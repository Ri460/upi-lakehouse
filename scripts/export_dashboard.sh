#!/usr/bin/env bash
set -euo pipefail
bucket=$(terraform -chdir=infra output -raw bucket)
aws s3 cp "s3://$bucket/exports/dashboard.json" docs/dashboard.json
printf 'Exported synthetic aggregates. Commit docs/dashboard.json to publish through GitHub Pages.
'
