#!/usr/bin/env bash
set -euo pipefail
: "${AWS_REGION:=ap-south-1}"
: "${ECR_REPOSITORY:?Set ECR_REPOSITORY to bootstrap repository_url}"
: "${TF_STATE_BUCKET:?Set TF_STATE_BUCKET to bootstrap state_bucket}"
: "${TF_VAR_alert_email:?Set TF_VAR_alert_email}"
tag=$(git rev-parse --short HEAD 2>/dev/null || date +%s)
registry=${ECR_REPOSITORY%%/*}
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"
docker build --platform linux/amd64 -t "$ECR_REPOSITORY:$tag" .
docker push "$ECR_REPOSITORY:$tag"
repo=${ECR_REPOSITORY#*/}
digest=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$repo" --image-ids imageTag="$tag" --query 'imageDetails[0].imageDigest' --output text)
export TF_VAR_image_uri="$ECR_REPOSITORY@$digest"
terraform -chdir=infra init -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="key=upi/demo.tfstate" -backend-config="region=$AWS_REGION" -backend-config="use_lockfile=true"
terraform -chdir=infra plan -out=deploy.tfplan
if [[ "${CI:-}" != "true" ]]; then
  read -r -p "Apply the reviewed plan? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || exit 0
fi
terraform -chdir=infra apply deploy.tfplan
