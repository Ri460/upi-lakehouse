import json
import os
import uuid
import boto3
import pytest
from src.validator import handler as validator
from src.producer.main import generate


@pytest.mark.skipif(
    os.getenv("RUN_LOCALSTACK") != "1", reason="start Docker LocalStack and set RUN_LOCALSTACK=1"
)
def test_real_aws_protocol_ingestion(monkeypatch):
    session = boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name="ap-south-1")
    opts = {"endpoint_url": "http://localhost:4566"}
    s3 = session.client("s3", **opts)
    sqs = session.client("sqs", **opts)
    db = session.resource("dynamodb", **opts)
    suffix = uuid.uuid4().hex[:8]
    bucket = f"local-{suffix}"
    table_name = f"txn-{suffix}"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    table = db.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "txn_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "txn_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    queue = sqs.create_queue(QueueName=f"invalid-{suffix}")["QueueUrl"]
    monkeypatch.setenv("BUCKET", bucket)
    monkeypatch.setenv("DLQ_URL", queue)
    monkeypatch.setattr(validator, "clients", lambda: (s3, sqs, table))
    event = next(generate(1, bad_rate=0))[0]
    records = [{"messageId": str(i), "body": json.dumps(event)} for i in range(2)]
    try:
        assert validator.handler({"Records": records}, None)["batchItemFailures"] == []
        assert s3.list_objects_v2(Bucket=bucket, Prefix="bronze/")["KeyCount"] == 1
        assert table.scan()["Count"] == 1
        assert table.get_item(Key={"txn_id": event["txn_id"]})["Item"]["status_ingest"] == "BRONZE_WRITTEN"
    finally:
        for item in s3.list_objects_v2(Bucket=bucket).get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=item["Key"])
        s3.delete_bucket(Bucket=bucket)
        sqs.delete_queue(QueueUrl=queue)
        table.delete()
