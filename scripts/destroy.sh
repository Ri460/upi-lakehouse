#!/usr/bin/env bash
set -euo pipefail
: "${TF_VAR_image_uri:?Set to deployed digest (see Terraform state or deploy output)}"
: "${TF_VAR_alert_email:?Set the same alert email}"
# Explicit opt-in: deletes this project's lake data along with its resources.
terraform -chdir=infra apply -var=allow_destroy_data=true
terraform -chdir=infra destroy -var=allow_destroy_data=true
printf 'Session resources removed. Bootstrap ECR and state storage remain; see docs/DEPLOY.md.
'
