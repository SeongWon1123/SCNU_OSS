#!/usr/bin/env bash
# ecr-create.sh — ECR 리포지토리 2개 생성 (SPEC §9.1: build.yml이 push하는 대상).
# 실행은 사람 게이트. 멱등: 이미 있으면 건너뛴다.
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"

for REPO in repodoc-api repodoc-caddy; do
  if aws ecr describe-repositories --region "$REGION" \
      --repository-names "$REPO" >/dev/null 2>&1; then
    echo "exists: $REPO"
  else
    aws ecr create-repository --region "$REGION" \
      --repository-name "$REPO" \
      --image-scanning-configuration "scanOnPush=true" \
      --image-tag-mutability MUTABLE
    echo "created: $REPO"
  fi
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "ECR_REGISTRY=${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
