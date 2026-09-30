# Verification status

Verified in the authoring environment:

- Python 3.12 environment resolves and installs `requirements.txt`.
- `pytest`: **23 passed, 1 skipped**. Skipped: Docker LocalStack integration.
- Ruff lint passes; Python sources formatted.
- Local synthetic demo: 5,000 inputs, 4,838 unique accepted, 124 malformed rejected, 38 exact duplicates removed, zero replay duplicates.
- Shared gold SQL executed against DuckDB in the local demo.
- Terraform formatting passes; JSON configuration files parse.
- Dashboard script syntax and workflow YAML parse checks pass.

Not verified here:

- Docker image build / LocalStack integration: no Docker daemon available.
- Full Terraform provider validation / tflint / AWS plan: provider startup requires a Unix socket that this environment blocks. Terraform/provider downloads and initialization succeeded, but schema validation could not execute. This is not an AWS deployment success.
- AWS IAM/service behavior, end-to-end cloud execution, p95, Athena benchmark, actual cost, dbt alternative.
- Browser visual rendering and public GitHub Pages publication.
- Live demo recording: a three-minute recording guide is included.

Run CI and a small AWS smoke session before claiming deployability or publishing cloud performance. Treat any provider/IAM errors found there as deployment fixes, not measured successes. The stack has intentionally conservative row/byte bounds and is designed as an educational project.
