# Deploy a short AWS session

## 1. Prepare the account

Use a dedicated learning account. Enable root MFA; never create root access keys. Prefer IAM Identity Center and `aws configure sso` / `aws sso login`. Check your AWS Free plan service access and credit expiry in Billing before enabling services. Accounts, eligibility, region prices and credit offers vary. The budget is not a spending cap and alerts can lag usage. Confirm `ap-south-1` supports your selected services and plan. Use `ingest_mode="sqs"` if Kinesis is unavailable.

Install Python 3.12, AWS CLI v2, Docker and Terraform >=1.10. Sign in with a bootstrap administrator. No credentials belong in this repo. On Windows, run shell scripts in WSL or Git Bash. Use the same project name in bootstrap and the main stack.

## 2. One-time bootstrap

```bash
export AWS_REGION=ap-south-1
export AWS_DEFAULT_REGION=ap-south-1
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap apply -var='github_repository=YOUR_NAME/YOUR_REPO'
```

If the account already has the GitHub OIDC provider, pass `-var='existing_oidc_provider_arn=arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com'` rather than creating a duplicate.

Bootstrap creates an ECR repository, a protected/versioned/encrypted Terraform-state bucket, and a repository-restricted OIDC deployment role. Keep bootstrap state secure and backed up: it initially lives on your machine. **The deployment role has broad control over the demo's service types, and project-prefixed IAM roles/S3 buckets. Use a dedicated sandbox account.** It is not an organization-wide production policy. Runtime Lambda roles are narrower. Review bootstrap IAM before applying.

Protect GitHub environments `aws-demo` and `aws-plan` with required reviewers and branch policies. The latter allows same-repository PR plans only after human approval; fork PRs receive credential-free checks. Never approve arbitrary PR code to run with AWS credentials. The bootstrap role only trusts the exact repository and those environment names.

Set repository variables:

| Variable | Value |
|---|---|
| AWS_DEPLOY_ROLE | bootstrap `deploy_role_arn` |
| TF_STATE_BUCKET | bootstrap `state_bucket` |
| ECR_REPOSITORY | bootstrap `repository_url` |
| ALERT_EMAIL | your email address |
| INGEST_MODE | `kinesis` or `sqs` |
| IMAGE_URI | digest URI after first image push, used for PR plans and destroy |

## 3. First deploy

```bash
export TF_STATE_BUCKET=$(terraform -chdir=infra/bootstrap output -raw state_bucket)
export ECR_REPOSITORY=$(terraform -chdir=infra/bootstrap output -raw repository_url)
export TF_VAR_alert_email='you@example.com'
export TF_VAR_ingest_mode=kinesis
bash scripts/deploy.sh
```

The script pushes a Linux amd64 container and uses an immutable image digest in Terraform. Review its saved plan. It prompts before applying. Save the digest URI printed in the plan as repository variable `IMAGE_URI`, and export it locally as `TF_VAR_image_uri` for teardown. Terraform uses S3 locking. On another platform, refresh provider checksums with `terraform -chdir=infra providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=windows_amd64`.

Confirm the SNS subscription email. Check Billing budget notifications. Schedule defaults OFF. Do not enable it until you have run a manual batch successfully. The bootstrap incurs ECR/state storage charges even when session resources are destroyed.

For subsequent sessions, the **AWS session** GitHub workflow can deploy or destroy with OIDC. Inspect CI results and the approved plan first. A $10 budget sends notifications at 50% and 80%; the $100 overall project allocation is your manual spending limit.

## 4. Produce a small burst

```bash
python -m src.producer.main --stream "$(terraform -chdir=infra output -raw stream)" --count 1000 --rate 20
# SQS fallback:
# python -m src.producer.main --queue-url "$(terraform -chdir=infra output -raw queue_url)" --count 1000 --rate 20
```

Wait for iterator age/backlog to settle. Expect quarantine notifications from deliberately bad events. Stop production before starting a batch for a consistent demo input set. `event_ts` is set at production time for AWS mode; exact replays retain their original timestamp.

```bash
aws stepfunctions start-execution --state-machine-arn "$(terraform -chdir=infra output -raw state_machine_arn)" --input '{}'
```

Inspect the returned execution ARN in Step Functions until it succeeds. Check `quality/<run>.json`, Parquet outputs, and Glue Catalog tables. If rejected by plan limits, use SQS or reconsider service access before upgrading your account.

## 5. Query the authenticated API

```bash
python scripts/call_api.py "$(terraform -chdir=infra output -raw api_url)/merchant/m000/summary"
python scripts/call_api.py "$(terraform -chdir=infra output -raw api_url)/txn/REPLACE_WITH_REAL_TXN_ID"
```

The caller needs `execute-api:Invoke` on this API ARN. The OIDC deploy role is not a viewer identity; grant a separate caller policy or use your sandbox admin. Requests use SigV4. No unauthenticated transaction endpoint is exposed. `/txn` returns the validated transaction and ingest state; fraud flags are batch analytics, not live fraud decisions in this route.

## 6. Publish the dashboard

```bash
bash scripts/export_dashboard.sh
```

Create your GitHub repository, commit this project, and push to `main`. In repository Settings → Pages choose GitHub Actions. The supplied Pages workflow publishes `docs/`, including snapshot JSON, and returns the live URL. This needs your GitHub account; no public repository has been created for you. Only synthetic aggregates should be published. The dashboard explicitly labels local versus AWS snapshots. It is not a live AWS query client.

## 7. Tear down every session

Stop the producer, wait for or stop active state-machine executions, export your snapshot and benchmarks, then:

```bash
export TF_VAR_image_uri='YOUR_ECR_REPOSITORY@sha256:YOUR_DIGEST'
bash scripts/destroy.sh
```

The script first applies `allow_destroy_data=true` so S3's destructive setting is stored in state, then destroys session resources. Both commands prompt. This permanently deletes this demo's lake contents. Keep exports before running it. Verify no Kinesis stream, Lambda, schedule, log group, table or Athena workgroup remains. Console-created resources are not covered by Terraform destroy.

Bootstrap remains: retain the small protected state bucket for the next session; ECR retains at most three images. For final project cleanup, first archive the state securely, empty/version-purge the state bucket, intentionally remove its `prevent_destroy` guard, then destroy bootstrap with its original variables. Do not delete a shared GitHub OIDC provider. This final cleanup is intentionally manual because losing the only state copy can orphan resources.

## Failure and replay runbook

- **Invalid business data:** inspect S3 quarantine through the SQS pointer, correct the record, send it with a new ID if its meaning changed. An identical valid event ID/body is a harmless replay; a changed body on an existing ID is rejected.
- **Transient S3/DynamoDB failure:** partial batch response triggers retries. Kinesis retries exhausted → complete invocation payload to the lake's `aws/lambda/` prefix. Download it and replay the embedded original records; a failure destination record is not itself an event. SQS exhaustion uses DLQ redrive. Monitor failure payload arrival and Lambda errors.
- **Quality failure:** read the GX report. The old silver catalog location is unchanged. Correct the source and start a new execution; do not manually fabricate a PASS marker.
- **Gold failure:** silver may already be current. Gold tables may have different run snapshots; retry the full pipeline after fixing the issue. Merchant API `CURRENT` remains old until every new summary is written.
- **Hard execution termination:** verify no batch is active, then wait for the two-hour lock lease or delete only `pk=LOCK` in the serve table. Never delete a live run's lock.
- **Late records:** next full batch rereads all retained bronze and recomputes history. Limits are 10,000 retained records and 16 MiB compressed. This is a bounded educational batch, not a large production workload.
