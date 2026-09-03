#!/usr/bin/env bash
# ssm-put.sh — SSM Parameter Store에 OPENAI_* 등록 (SPEC §9.3 주입 전제).
# 실행은 사람 게이트. 값은 환경변수로 받는다(원문을 히스토리/출력에 남기지 않는다):
#   OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
#     OPENAI_MODEL=... bash deploy/ssm-put.sh
# 주입 경로(deploy.sh): EC2 호스트(awscli + 인스턴스 롤 ssm:GetParameter /repodoc/*)가
# get-parameter로 읽어 /opt/repodoc/.env에 기록 → compose env_file로 컨테이너 주입.
# 참고: 동결안은 컨테이너 entrypoint의 aws ssm get-parameter였으나 api 이미지에
# awscli가 없어(오라클 지적) 호스트 fetch 방식을 채택 — docs/DEPLOY.md와 PR ⑥ 기록.
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY 환경변수가 필요하다}"
: "${OPENAI_BASE_URL:?OPENAI_BASE_URL 환경변수가 필요하다(예: https://openrouter.ai/api/v1)}"
: "${OPENAI_MODEL:?OPENAI_MODEL 환경변수가 필요하다}"

put() {
  aws ssm put-parameter --region "$REGION" \
    --name "/repodoc/$1" --type SecureString --overwrite \
    --value "$2" >/dev/null
  echo "put: /repodoc/$1 (SecureString)"
}

put OPENAI_API_KEY "$OPENAI_API_KEY"
put OPENAI_BASE_URL "$OPENAI_BASE_URL"
put OPENAI_MODEL "$OPENAI_MODEL"
