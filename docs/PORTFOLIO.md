# Portfolio handoff

## Before publishing

- Replace repository placeholders; create the GitHub repo and configure protected AWS environments.
- Run CI on GitHub including LocalStack, Terraform validate and tflint.
- Deploy a short session; exercise every state and both API routes.
- Export AWS snapshot, cloud benchmarks and actual cost, then destroy.
- Enable GitHub Pages and record the demo with the supplied script.
- Add CI badge, dashboard URL and demo video URL to README only after they exist.

## Truthful bullets now

- Developed a streaming and batch transaction lakehouse project with Terraform, Lambda, Great Expectations, Athena and DynamoDB, including a runnable local demo and automated failure/replay tests.
- Implemented immutable transaction IDs, replay deduplication, schema-version validation and quality-gated Parquet publication for synthetic UPI/e-commerce events.

## Replace with measured cloud results later

- Deployed an AWS transaction lakehouse processing **[measured events/min]** at **[measured p95 ms]** ingestion latency using Kinesis, Lambda, S3 and Athena.
- Rejected **[malformed catch rate]%** of injected malformed records and verified zero duplicate silver transaction IDs after replaying **[N]** events.
- Reduced Athena scanned bytes by **[N]%** using partitioned Parquet versus the same filtered query on JSON; completed the demo at **$[gross] / $[net after credits]**.

Do not claim million-event scale, deployed cloud performance, production-grade fraud detection or exact cost savings from a local demo.
