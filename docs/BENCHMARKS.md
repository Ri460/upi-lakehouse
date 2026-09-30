# Benchmarks: evidence, not targets

The bundled `benchmarks.json` contains a real local run of 5,000 seeded synthetic events. It records malformed-event catch rate, duplicate removal, replay output, local filesystem ingest p95 and JSON/Parquet file bytes. These measurements are machine-specific. The local JSON/Parquet comparison also includes silver-derived columns, so treat it as an illustrative storage comparison rather than an isolated encoding experiment.

Cloud performance and billing fields are deliberately null. Do not describe local p95 as AWS p95 or file-size reduction as Athena query-cost savings.

## Reproduce locally

```bash
python -m src.local_demo --count 5000
python -m pytest -q
```

Malformed catch rate denominator excludes exact duplicates: duplicates are valid replays and removed separately. `invalid_rejected / injected_malformed` is the catch rate. Silver replay test concatenates accepted records with the identical accepted records and verifies unique transaction IDs.

## Capture AWS latency and throughput

Run a clean benchmark with `--bad-rate 0` for an unambiguous success denominator. Use distinct seed/event IDs on a fresh stack. Count persisted unique transaction IDs and record wall-clock run duration. Sustained events/minute = unique bronze-complete events / elapsed ingestion minutes, including drain time. Do not report producer-request rate as ingestion throughput.

Validator emits CloudWatch Embedded Metric Format `UPILakehouse / BronzeLatencyMs` with `Pipeline=upi-lakehouse`; capture p95 for the exact test window. It measures producer event timestamp to completion of S3 PutObject, including queue time and network. Replays retain old timestamps, so exclude replay runs from latency benchmarks. CloudWatch logs retain 7 days. Cold starts should be included or reported separately.

## Compare Athena scanned bytes

`python scripts/benchmark_athena.py --bucket BUCKET --database DB --workgroup WORKGROUP` uses the local demo's silver rows to create three identical benchmark datasets: NDJSON, unpartitioned Parquet, partitioned Parquet. All are queried with the same date/hour filter and successful-payment revenue expression. It checks answer equality, disables result reuse, and writes query IDs, bytes scanned and engine time to `data/athena-benchmark.json`.

Run after the local demo and AWS deployment, while the 100 MB/query workgroup cutoff is active. Partitioning benefits require multiple partitions; use the 5,000-row demo. Record small-data minimum billing effects separately. Scanned-byte differences are not your full AWS bill. Dataset preparation also creates chargeable S3 requests and Athena metadata.

## Cost worksheet

Use Billing console actual usage and credits separately, after usage has settled. Record date, region, session duration, Kinesis shard-hours, S3 storage/requests, Athena bytes/queries, Lambda duration/memory/requests, DynamoDB requests, CloudWatch logs/alarms, X-Ray traces, ECR storage, SNS and Step Functions. Capture total gross charges and net payable after credits. Budget alarms do not enforce shutdown.

Sources (verify before spending):
- https://aws.amazon.com/kinesis/data-streams/pricing/
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/athena/pricing/
- https://aws.amazon.com/cloudwatch/pricing/
- https://aws.amazon.com/ecr/pricing/
- https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html

The brief's $10–$25 estimate is a planning assumption, not a measured bill or a guaranteed price. This build avoids paid Glue ETL jobs, but still uses the Glue Catalog. A $100 budget is not automatically enforced by these Terraform resources.
