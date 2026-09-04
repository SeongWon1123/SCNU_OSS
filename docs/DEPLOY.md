# DEPLOY — 배포 재현 절차 (Phase 6, 사람 게이트)

> **실행은 사람이 한다.** 이 문서와 `deploy/` 스크립트는 산출물이며, 에이전트는 AWS 자원을 만들지 않는다.
> 참조: `deploy/provision.sh`(§9.2), `deploy/deploy.sh`(§9.3).

## 굵은 금지 3종 (전 구간 적용)

1. **`docker compose down -v` 금지** — 볼륨(db_data·caddy_data) 삭제는 인증서·DB를 파괴한다. 스택 정지는 `docker compose down`(볼륨 유지)만.
2. **EIP 재할당 금지** — Route 53 A 레코드와 `FALLBACK_DOMAIN`이 고정된다. 재할당 시 도메인·인증서 재작업.
3. **9/23 이후 stop 금지** — 전시 기간 중 인스턴스 정지(재부팅만 허용). stop하면 public IPv4 과금 정책과 세션이 어긋난다(§9.4).

## 0. 사전 준비

- AWS 계정 + 크레딧(예산 $20 — §9.5), 로컬에 AWS CLI 자격증명(`aws sts get-caller-identity` 확인).
- 도메인: Route 53에서 `.click`/`.link` 1개 등록(§9.4), A 레코드를 EIP로.
- 로컬 `.env` 준비(`cp .env.example .env`) — `DATABASE_URL`, `GITHUB_TOKEN`, `MAX_*`, `DOMAIN`, `FALLBACK_DOMAIN`, `ACME_EMAIL`. **`OPENAI_API_KEY`는 .env에 넣지 않는다(아래 2단계 SSM).**
- 이미지 공급: main 머지 시 `.github/workflows/build.yml`이 `repodoc-api`·`repodoc-caddy`(git sha + latest 태그)를 ECR에 push. EC2에서 `docker build`·`next build` 금지.

## 1. ECR 리포지토리 생성

```bash
bash deploy/ecr-create.sh   # repodoc-api, repodoc-caddy (ap-northeast-2, 멱등)
```

출력의 `ECR_REGISTRY=<계정>.dkr.ecr.ap-northeast-2.amazonaws.com`을 기록.

## 2. SSM 파라미터 등록 (OPENAI_* — SecureString)

```bash
OPENAI_API_KEY=sk-... \
OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
OPENAI_MODEL=<모델명> \
bash deploy/ssm-put.sh
# → /repodoc/OPENAI_API_KEY, /repodoc/OPENAI_BASE_URL, /repodoc/OPENAI_MODEL
```

### OPENAI_* 주입 경로와 awscli 부재 문제

- **경로**: EC2 호스트의 `awscli`(user-data 설치) + 인스턴스 롤(`ssm:GetParameter /repodoc/*`)이 기동 시 읽고, `deploy.sh`가 `/opt/repodoc/.env`에 기록 → compose `env_file`로 컨테이너 주입 → `chmod 600`.
- **awscli 부재 문제**: 동결안은 컨테이너 entrypoint에서 `aws ssm get-parameter`였으나 api 이미지에 awscli가 없어 불가. 대안으로 deploy.sh가 호스트에서 fetch해 .env로 생성(오라클 지적 반영 — PR ⑥ 편차 기록).

## 3. EC2 프로비저닝 (provision.sh — §9.2)

```bash
bash deploy/provision.sh <ec2-keypair-name>
# ap-northeast-2 · Ubuntu 24.04 · t3.small · 루트 30GB gp3 ·
# SG 80/443만(22 없음) · IAM 롤(ECR pull, S3 put, SSM get-parameter, CloudWatch put) ·
# user-data: 스왑 2GB · docker+compose+awscli+CW agent+SSM agent ·
# 로그 로테이션 10m×3 · /var/scan 30분 cron 정리 · repodoc-ready ·
# EIP 할당·연결
```

출력된 `INSTANCE_ID`·`EIP` 기록 → Route 53 A 레코드를 EIP로. `FALLBACK_DOMAIN=<dash-EIP>.sslip.io`를 `.env`에 반영.

## 4. 배포 (deploy.sh — §9.3)

SSH 22가 없으므로 **SSM Session Manager 포트포워딩 터널** 경유:

```bash
# 터미널 A (유지)
aws ssm start-session --region ap-northeast-2 --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["22"],"localPortNumber":["2222"]}'

# 터미널 B
INSTANCE_ID=<인스턴스> ECR_REGISTRY=<계정>.dkr.ecr.ap-northeast-2.amazonaws.com \
  bash deploy/deploy.sh
```

deploy.sh 내부 순서: 터널 확인 → `cloud-init status --wait && test -f repodoc-ready` → `rsync -az --delete --exclude-from=deploy/rsync-exclude`(대상: .git, node_modules, .next, out, .env, __pycache__, web/node_modules) → `.env` scp + chmod 600 → ECR 로그인 → SSM fetch로 .env의 OPENAI_* 갱신 → `docker compose pull && up -d --remove-orphans`(ECR image: 오버라이드 `docker-compose.ecr.yml` 자동 생성) → `docker image prune -af --filter until=48h` → `/api/health` 3회 확인, 실패 시 이전 태그(`.last_tag`) 재배포(롤백).

## 5. 검증 (SPEC §9 DoD)

1. `https://<도메인>`에서 타인 공개 리포 스캔 성공(폰) — 최초 발급은 스테이징 CA(Caddyfile 주석 토글)로 성공 확인 후 운영 CA로 1회 전환.
2. `sudo reboot` 후 3분 내 `curl https://<도메인>/api/health` OK.
3. `docker compose exec worker id` → uid 10001.
4. 2GB 초과 체크아웃 시도가 failed로 정리되고 다음 스캔 정상.
5. `df -h` 루트 30GB 확인.
6. CloudWatch 알람 2개(StatusCheckFailed, 디스크 ≥80%) 적용: `deploy/cloudwatch.json`의 `<ACCOUNT_ID>`·`<INSTANCE_ID>` 치환 후 `aws cloudwatch put-metric-alarm --cli-input-json file://deploy/cloudwatch.json`. SNS 구독 확인 메일 승인 캡처.
7. 예산: `bash deploy/sns-budgets.sh`(EMAIL·ACCOUNT_ID) — Budgets $20, 80% 실제·100% 예측 알림.

## env 변수 목록

| 변수 | 위치 | 비고 |
|---|---|---|
| `OPENAI_API_KEY` | SSM `/repodoc/OPENAI_API_KEY`(SecureString) | .env에 두지 않음, deploy.sh가 주입 |
| `OPENAI_BASE_URL` | SSM `/repodoc/OPENAI_BASE_URL` | 예: `https://openrouter.ai/api/v1` |
| `OPENAI_MODEL` | SSM `/repodoc/OPENAI_MODEL` | OpenRouter 모델명 |
| `GITHUB_TOKEN` | 로컬 .env → scp | 공개 리포 API 레이트리밋 완화 |
| `DOMAIN` | 로컬 .env → scp | Route 53 도메인 |
| `FALLBACK_DOMAIN` | 로컬 .env → scp | `<dash-EIP>.sslip.io` |
| `ACME_EMAIL` | 로컬 .env → scp | Let's Encrypt 알림 메일 |
| `DATABASE_URL`, `MAX_FILES`, `MAX_FILE_MB`, `MAX_TOTAL_MB`, `DAILY_LIMIT_PER_IP`, `RATE_LIMIT_BYPASS_IPS`, `S3_BUCKET`, `OPENAI_MODEL_FALLBACK` | 로컬 .env → scp | `.env.example` 참조 |

## 롤백 절차

- 자동: deploy.sh가 `/api/health` 3회 실패 시 `.last_tag`(직전 성공 태그)로 재배포.
- 수동: `IMAGE_TAG=<직전 sha> ECR_REGISTRY=... bash deploy/deploy.sh` 재실행. 또는 EC2에서 `docker compose -f docker-compose.yml -f docker-compose.ecr.yml up -d --remove-orphans` (이미지 태그 교체 후).
- **절대 `docker compose down -v`로 되돌리지 않는다** — 볼륨 유지가 롤백의 전제다.

## SSH 대신 SSM Session Manager

- 보안그룹에 22가 없다(설계). 셸 접속: `aws ssm start-session --region ap-northeast-2 --target "$INSTANCE_ID"`(AWS CLI에 session-manager 플러그인 필요).
- 파일 전송·rsync는 4단계처럼 `AWS-StartPortForwardingSession`(22→localhost:2222) 터널 위에서 수행.
- 콘솔 대안: EC2 콘솔 → Connect → Session Manager.
