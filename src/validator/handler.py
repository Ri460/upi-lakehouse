import base64
import gzip
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from src.common.contract import InvalidEvent, canonical, digest, normalize, partition


def clients():
    return boto3.client("s3"), boto3.client("sqs"), boto3.resource("dynamodb").Table(os.environ["TXN_TABLE"])


def handler(event, context):
    s3, sqs, table = clients()
    failures = []
    for record in event.get("Records", []):
        is_stream = "kinesis" in record
        identifier = record["kinesis"]["sequenceNumber"] if is_stream else record["messageId"]
        raw = base64.b64decode(record["kinesis"]["data"]) if is_stream else record["body"].encode()
        try:
            try:
                item = normalize(json.loads(raw))
                fingerprint = digest(item)
                try:
                    # Immutable ID. Same content can repeat; changed content cannot silently overwrite it.
                    table.put_item(
                        Item={
                            "txn_id": item["txn_id"],
                            "hash": fingerprint,
                            "payload": canonical(item),
                            "status_ingest": "ACCEPTED",
                        },
                        ConditionExpression="attribute_not_exists(txn_id) OR #h = :h",
                        ExpressionAttributeNames={"#h": "hash"},
                        ExpressionAttributeValues={":h": fingerprint},
                    )
                except ClientError as exc:
                    if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                        raise InvalidEvent("conflicting txn_id") from exc
                    raise
            except (InvalidEvent, json.JSONDecodeError, UnicodeDecodeError) as exc:
                import hashlib

                key = f"quarantine/{hashlib.sha256(raw).hexdigest()}.json"
                quarantine = json.dumps({"reason": str(exc), "raw_base64": base64.b64encode(raw).decode()})
                s3.put_object(Bucket=os.environ["BUCKET"], Key=key, Body=quarantine.encode())
                sqs.send_message(
                    QueueUrl=os.environ["DLQ_URL"],
                    MessageBody=json.dumps({"bucket": os.environ["BUCKET"], "key": key, "reason": str(exc)}),
                )
                print(json.dumps({"outcome": "rejected", "reason": str(exc)}))
                continue
            key = f"bronze/{partition(item)}/{item['txn_id']}-{fingerprint}.ndjson.gz"
            # Deterministic gzip bytes and key: retries repair an interrupted DynamoDB -> S3 write.
            s3.put_object(
                Bucket=os.environ["BUCKET"],
                Key=key,
                Body=gzip.compress((canonical(item) + "\n").encode(), mtime=0),
                ContentType="application/x-ndjson",
                ContentEncoding="gzip",
            )
            now = datetime.now(timezone.utc)
            latency = max(0, (now - datetime.fromisoformat(item["event_ts"])).total_seconds() * 1000)
            table.update_item(
                Key={"txn_id": item["txn_id"]},
                UpdateExpression="SET status_ingest=:s, bronze_latency_ms=:l",
                ExpressionAttributeValues={":s": "BRONZE_WRITTEN", ":l": Decimal(str(round(latency, 3)))},
            )
            print(
                json.dumps(
                    {
                        "_aws": {
                            "Timestamp": int(time.time() * 1000),
                            "CloudWatchMetrics": [
                                {
                                    "Namespace": "UPILakehouse",
                                    "Dimensions": [["Pipeline"]],
                                    "Metrics": [{"Name": "BronzeLatencyMs", "Unit": "Milliseconds"}],
                                }
                            ],
                        },
                        "Pipeline": os.environ.get("PIPELINE", "upi"),
                        "BronzeLatencyMs": latency,
                        "outcome": "accepted",
                    }
                )
            )
        except Exception:
            # Infrastructure errors must retry; do not relabel them as invalid business data.
            failures.append({"itemIdentifier": identifier})
            print(json.dumps({"outcome": "retry", "identifier": identifier}))
    return {"batchItemFailures": failures}
