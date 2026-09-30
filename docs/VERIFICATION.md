# Verification status

Verified in the authoring environment:

- Python 3.12 environment resolves and installs `requirements.txt`.
- `pytest`: **23 passed, 1 skipped**. Skipped: Docker LocalStack integration.
- Ruff lint passes; Python sources formatted.
- Local synthetic demo: 5,000 inputs, 4,838 unique accepted, 124 malformed rejected, 38 exact duplicates removed, zero replay duplicates.
- Shared gold SQL executed against DuckDB in the local demo.
- Terraform formatting passes; JSON configuration files parse.
- Dashboard script syntax and workflow YAML parse checks pass.
- Latest GitHub Actions CI run passed Ruff, pytest, the LocalStack integration, Terraform validation, and TFLint.
- GitHub Pages publication completed successfully and the public page was visually verified at https://ri460.github.io/upi-lakehouse/. It serves an AWS synthetic-data export from 2026-09-30 20:39 UTC: 376 accepted unique transactions, ₹853,722 revenue, 1.9% flagged, 12 merchants.

Not verified here:

- Lambda image build/push to ECR and a clean end-to-end AWS deployment from this repository.
- AWS IAM/service behavior, current runtime/API availability, cloud p95, Athena benchmark, actual cost, and dbt alternative. Account SCP restrictions previously denied GitHub OIDC provider creation and Kinesis stream tagging.
- Live demo recording: a three-minute recording guide is included.

Run CI and a small AWS smoke session before claiming deployability or publishing cloud performance. Treat any provider/IAM errors found there as deployment fixes, not measured successes. The stack has intentionally conservative row/byte bounds and is designed as an educational project.
