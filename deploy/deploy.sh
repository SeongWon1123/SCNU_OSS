#!/usr/bin/env bash
# deploy.sh — EC2 배포 (SPEC §9.3). 개발 머신에서 실행, 사람 게이트.
# 접속은 SSM Session Manager 포트포워딩 터널 경유(보안그룹에 22가 없다):
#   aws ssm start-session --region ap-northeast-2 \
#     --target "$INSTANCE_ID" \
#     --document-name AWS-StartPortForwardingSession \
#     --parameters '{"portNumber":["22"],"localPortNumber":["2222"]}'
# 사전 요건: build.yml이 push한 ECR 이미지, /opt/repodoc 소유 ubuntu, 로컬 .env(비밀 제외—OPENAI_*는 SSM).
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"
INSTANCE_ID="${INSTANCE_ID:?INSTANCE_ID 환경변수가 필요하다}"
ECR_REGISTRY="${ECR_REGISTRY:?ECR_REGISTRY 환경변수가 필요하다(<계정>.dkr.ecr.ap-northeast-2.amazonaws.com)}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PREV_TAG="${PREV_TAG:-}"           # 롤백 대상 태그. 비우면 /opt/repodoc/.last_tag 사용.
SSH_PORT="${SSH_PORT:-2222}"
SSH_KEY="${SSH_KEY:-}"             # 필요 시 -i 키 경로.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SSH_E="ssh -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
[ -n "$SSH_KEY" ] && SSH_E="$SSH_E -i $SSH_KEY"
SCP_E="scp -P $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
[ -n "$SSH_KEY" ] && SCP_E="$SCP_E -i $SSH_KEY"
TARGET="ubuntu@localhost"

echo "[0/5] 터널 확인 — 위 start-session 명령이 떠 있어야 한다."
$SSH_E "$TARGET" true

echo "[1/5] cloud-init 완료 + repodoc-ready 대기."
$SSH_E "$TARGET" 'cloud-init status --wait && test -f /var/lib/cloud/instance/repodoc-ready'

echo "[2/5] rsync 리포 동기화(--delete) + .env 전송(chmod 600)."
rsync -az --delete --exclude-from="$REPO_DIR/deploy/rsync-exclude" \
  -e "$SSH_E" "$REPO_DIR/" "$TARGET:/opt/repodoc/"
if [ -f "$REPO_DIR/.env" ]; then
  $SCP_E "$REPO_DIR/.env" "$TARGET:/opt/repodoc/.env"
fi

echo "[3/5] ECR 로그인 → SSM 주입 → compose pull && up -d --remove-orphans."
if ! $SSH_E "$TARGET" \
    "REGION='$REGION' ECR_REGISTRY='$ECR_REGISTRY' IMAGE_TAG='$IMAGE_TAG' PREV_TAG='$PREV_TAG' bash -s" <<'REMOTE'
set -euo pipefail
cd /opt/repodoc
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# OPENAI_* 주입: 컨테이너 이미지에 awscli가 없어(오라클 지적) 호스트에서 SSM을 읽어
# .env로 생성한다. 호스트 awscli + 인스턴스 롤(ssm:GetParameter /repodoc/*) 사용.
KEY=$(aws ssm get-parameter --name /repodoc/OPENAI_API_KEY --with-decryption \
  --query Parameter.Value --output text)
BASE=$(aws ssm get-parameter --name /repodoc/OPENAI_BASE_URL --with-decryption \
  --query Parameter.Value --output text 2>/dev/null || true)
MODEL=$(aws ssm get-parameter --name /repodoc/OPENAI_MODEL --with-decryption \
  --query Parameter.Value --output text 2>/dev/null || true)
touch .env
sed -i '/^OPENAI_API_KEY=/d;/^OPENAI_BASE_URL=/d;/^OPENAI_MODEL=/d' .env
printf 'OPENAI_API_KEY=%s\nOPENAI_BASE_URL=%s\nOPENAI_MODEL=%s\n' "$KEY" "$BASE" "$MODEL" >> .env
chmod 600 .env

# compose는 로컬 개발용 build:만 있어 EC2 pull을 위해 image: 오버라이드가 필요하다(⑥).
cat > docker-compose.ecr.yml <<OVR
services:
  api:
    image: ${ECR_REGISTRY}/repodoc-api:${IMAGE_TAG}
  worker:
    image: ${ECR_REGISTRY}/repodoc-api:${IMAGE_TAG}
  caddy:
    image: ${ECR_REGISTRY}/repodoc-caddy:${IMAGE_TAG}
OVR
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.ecr.yml"

health_ok() {
  for i in 1 2 3; do
    if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
      echo "health OK (try $i)"; return 0
    fi
    echo "health 대기 $i/3"; sleep 10
  done
  return 1
}

LAST_TAG=
[ -f .last_tag ] && LAST_TAG=$(cat .last_tag)
PREV="${PREV_TAG:-${LAST_TAG:-}}"

$COMPOSE pull
$COMPOSE up -d --remove-orphans
docker image prune -af --filter until=48h

if health_ok; then
  echo "$IMAGE_TAG" > .last_tag
  echo "배포 성공: tag=$IMAGE_TAG"
  exit 0
fi

echo "헬스 실패 — 이전 태그로 롤백: prev=${PREV:-없음}"
if [ -n "$PREV" ] && [ "$PREV" != "$IMAGE_TAG" ]; then
  IMAGE_TAG="$PREV" $COMPOSE up -d --remove-orphans
  health_ok || true
  echo "롤백 완료(prev tag 재배포). 원인 조사 후 재배포할 것."
else
  echo "롤백 대상 태그가 없다. docker compose logs api로 원인 확인할 것."
fi
exit 1
REMOTE
then
  echo "[3/5] 원격 배포 실패 — 원격 스크립트의 롤백/로그 안내를 확인했다."
  exit 1
fi

echo "[4/5] /api/health 외부 확인(https://\$DOMAIN)."
DOMAIN=$(grep -E '^DOMAIN=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- || true)
if [ -n "${DOMAIN:-}" ]; then
  curl -fsS "https://$DOMAIN/api/health" || true
fi

echo "[5/5] 배포 절차 종료. 검증은 docs/DEPLOY.md 5단계(인증서·재부팅·worker id 10001·df -h)."
