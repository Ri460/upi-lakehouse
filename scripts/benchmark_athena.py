"""Run paid Athena comparison on three identical synthetic datasets."""

import argparse
import json
import time
from pathlib import Path
import awswrangler as wr
import boto3
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    for name in ["bucket", "database", "workgroup"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--input", default="data/demo/silver")
    args = parser.parse_args()
    frame = pd.read_parquet(args.input)[["amount_paise", "status", "dt", "hr"]]
    frame["dt"] = frame["dt"].astype(str)
    frame["hr"] = frame["hr"].astype(str)
    base = f"s3://{args.bucket}/benchmarks/"
    wr.s3.to_json(frame, path=base + "json/events.ndjson", orient="records", lines=True)
    wr.catalog.create_json_table(
        database=args.database,
        table="bench_json",
        path=base + "json/",
        columns_types={"amount_paise": "bigint", "status": "string", "dt": "string", "hr": "string"},
        mode="overwrite",
    )
    for table, partition_cols in [("bench_parquet", None), ("bench_partitioned", ["dt", "hr"])]:
        wr.s3.to_parquet(
            frame,
            path=base + table + "/",
            dataset=True,
            mode="overwrite",
            partition_cols=partition_cols,
            database=args.database,
            table=table,
            compression="snappy",
        )
    day, hour = frame.iloc[0][["dt", "hr"]]
    athena = boto3.client("athena")
    results = []
    for table in ["bench_json", "bench_parquet", "bench_partitioned"]:
        sql = f"SELECT sum(amount_paise) revenue_paise FROM {table} WHERE dt='{day}' AND hr='{hour}' AND status='SUCCESS'"
        query_id = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": args.database},
            WorkGroup=args.workgroup,
            ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": False}},
        )["QueryExecutionId"]
        deadline = time.monotonic() + 300
        while True:
            execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
            state = execution["Status"]["State"]
            if state == "SUCCEEDED":
                break
            if state in ["FAILED", "CANCELLED"]:
                raise RuntimeError(execution["Status"])
            if time.monotonic() > deadline:
                athena.stop_query_execution(QueryExecutionId=query_id)
                raise TimeoutError(query_id)
            time.sleep(1)
        rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
        value = rows[1]["Data"][0].get("VarCharValue")
        stats = execution["Statistics"]
        results.append(
            {
                "table": table,
                "query_id": query_id,
                "revenue_paise": value,
                "bytes_scanned": stats["DataScannedInBytes"],
                "engine_ms": stats.get("EngineExecutionTimeInMillis"),
                "filter": {"dt": day, "hr": hour},
            }
        )
    assert len({row["revenue_paise"] for row in results}) == 1, "Answers differ; benchmark invalid"
    Path("data").mkdir(exist_ok=True)
    Path("data/athena-benchmark.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
