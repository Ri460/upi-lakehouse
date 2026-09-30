import gzip
import io
import json
import os
import time

import boto3
import pandas as pd
from src.common.gold import QUERIES
from src.silver.transform import transform
from src.silver.quality import validate, require_pass


def handler(event, context):
    import awswrangler as wr

    bucket, database = os.environ["BUCKET"], os.environ["DATABASE"]
    s3 = boto3.client("s3")
    serve = boto3.resource("dynamodb").Table(os.environ["SERVE_TABLE"])
    run, op = event["run_id"], event["op"]
    if not run.replace("-", "").isalnum():
        raise ValueError("invalid run ID")
    staging = f"staging/{run}/candidate.parquet"
    if op == "release":
        try:
            serve.delete_item(
                Key={"pk": "LOCK"}, ConditionExpression="run_id = :r", ExpressionAttributeValues={":r": run}
            )
        except serve.meta.client.exceptions.ConditionalCheckFailedException:
            pass
        return event
    if op == "stage":
        serve.put_item(
            Item={"pk": "LOCK", "run_id": run, "lease_until": int(time.time()) + 7200},
            ConditionExpression="attribute_not_exists(pk) OR lease_until < :now OR run_id = :run",
            ExpressionAttributeValues={":now": int(time.time()), ":run": run},
        )
        records, size = [], 0
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="bronze/"):
            for item in page.get("Contents", []):
                if not item["Key"].endswith(".ndjson.gz"):
                    continue
                size += item["Size"]
                if size > int(os.getenv("MAX_BRONZE_BYTES", "16777216")):
                    raise ValueError("demo bronze byte limit exceeded; archive data or move batch to Glue")
                body = s3.get_object(Bucket=bucket, Key=item["Key"])["Body"].read()
                records.extend(json.loads(line) for line in gzip.decompress(body).splitlines())
                if len(records) > int(os.getenv("MAX_RECORDS", "10000")):
                    raise ValueError("demo row limit exceeded")
        frame = transform(records)
        buffer = io.BytesIO()
        frame.to_parquet(buffer, index=False, compression="snappy")
        s3.put_object(Bucket=bucket, Key=staging, Body=buffer.getvalue())
        return {"run_id": run, "rows": len(frame)}
    if op == "gate":
        frame = pd.read_parquet(io.BytesIO(s3.get_object(Bucket=bucket, Key=staging)["Body"].read()))
        report = validate(frame)
        s3.put_object(Bucket=bucket, Key=f"quality/{run}.json", Body=json.dumps(report, default=str).encode())
        require_pass(report)
        # This marker is checked again by publish. A direct call cannot skip the gate.
        s3.put_object(Bucket=bucket, Key=f"staging/{run}/PASSED", Body=b"pass")
        return {"run_id": run, "rows": len(frame)}
    if op == "publish":
        s3.head_object(Bucket=bucket, Key=f"staging/{run}/PASSED")
        frame = pd.read_parquet(io.BytesIO(s3.get_object(Bucket=bucket, Key=staging)["Body"].read()))
        # Snapshot path: readers keep the previous catalog location until this write completes.
        location = f"s3://{bucket}/silver/{run}/"
        wr.s3.to_parquet(
            df=frame,
            path=location,
            dataset=True,
            partition_cols=["dt", "hr"],
            mode="overwrite",
            compression="snappy",
        )
        wr.catalog.create_parquet_table(
            database=database,
            table="silver",
            path=location,
            columns_types={
                "txn_id": "string",
                "user_id": "string",
                "merchant_id": "string",
                "amount": "double",
                "currency": "string",
                "payment_method": "string",
                "status": "string",
                "city": "string",
                "device_id": "string",
                "event_ts": "timestamp",
                "schema_version": "bigint",
                "campaign_id": "string",
                "amount_paise": "bigint",
                "amount_spike": "boolean",
                "velocity_flag": "boolean",
                "is_fraud": "boolean",
            },
            partitions_types={"dt": "string", "hr": "string"},
            mode="overwrite",
            athena_partition_projection_settings={
                "projection_types": {"dt": "enum", "hr": "enum"},
                "projection_values": {
                    "dt": ",".join(sorted(frame.dt.unique())),
                    "hr": ",".join(sorted(frame.hr.unique())),
                },
                "projection_storage_location_template": location + "dt=${dt}/hr=${hr}/",
            },
        )
        return {"run_id": run, "rows": len(frame)}
    if op == "gold":
        gold = {}
        for name, sql in QUERIES.items():
            # Real Athena aggregation, then compact Parquet output and catalog registration.
            frame = wr.athena.read_sql_query(
                sql,
                database=database,
                ctas_approach=False,
                workgroup=os.environ["WORKGROUP"],
                s3_output=f"s3://{bucket}/athena-results/",
            )
            wr.s3.to_parquet(
                df=frame,
                path=f"s3://{bucket}/gold/{run}/{name}/",
                dataset=True,
                mode="overwrite",
                database=database,
                table=name,
                compression="snappy",
            )
            gold[name] = json.loads(frame.to_json(orient="records"))
        merchants = {}
        for row in gold["daily_merchant_revenue"]:
            summary = merchants.setdefault(
                row["merchant_id"],
                {
                    "merchant_id": row["merchant_id"],
                    "currency": "INR",
                    "transactions": 0,
                    "revenue_paise": 0,
                    "flagged_transactions": 0,
                    "run_id": run,
                },
            )
            for field in ["transactions", "revenue_paise", "flagged_transactions"]:
                summary[field] += row[field]
        with serve.batch_writer() as writer:
            for merchant, summary in merchants.items():
                writer.put_item(Item={"pk": f"{run}#{merchant}", "payload": json.dumps(summary)})
        # Flip only after all merchant summaries are present. No increment-on-replay counters.
        serve.put_item(Item={"pk": "CURRENT", "run_id": run})
        payload = {
            "source": "AWS synthetic demo",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "metrics": {"accepted_unique": sum(x["transactions"] for x in gold["payment_method_mix"])},
            **gold,
        }
        s3.put_object(
            Bucket=bucket,
            Key="exports/dashboard.json",
            Body=json.dumps(payload).encode(),
            ContentType="application/json",
        )
        return {"run_id": run, "merchants": len(merchants)}
    raise ValueError("unknown operation")
