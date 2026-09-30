# Optional dbt alternative

The deployed state machine uses Athena SQL through `src/common/gold.py`; it does not require dbt. This folder offers equivalent view models for learning or a later CI job. Do not run dbt concurrently with the gold Lambda.

Install `pip install 'dbt-athena>=1.9,<2'`, set AWS_REGION, LAKE_BUCKET, LAKE_DATABASE and ATHENA_WORKGROUP, then run `dbt build --project-dir dbt --profiles-dir dbt`. Models are prefixed `dbt_` to avoid overwriting the state machine's physical gold tables. Use a role with Athena, Glue metadata and project S3 permissions. Resolve and lock your dbt dependencies when adopting this alternative. It has not been exercised against AWS in this environment.
