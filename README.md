# 리포닥 (RepoDoc)

> GitHub 공개 저장소 URL 하나로 보안·라이선스·**한국 규제 준수**를 진단하는 오픈소스 클리닉.
> 2026 SCNU OSS·AI 해커톤 고급 트랙 출품작.

[![ci](https://github.com/SeongWon1123/SCNU_OSS/actions/workflows/ci.yml/badge.svg)](https://github.com/SeongWon1123/SCNU_OSS/actions/workflows/ci.yml)

<!-- TODO: 15초 데모 GIF (랜딩 → 스캔 → 93/A 결과) -->
<!-- TODO: 공개 실행 URL (EC2 배포 후 기입) -->
<!-- TODO: 아키텍처 SVG -->

"바이브코딩한 내 서비스, 배포해도 되나요?" — 위치정보 신고, 개인정보처리방침,
통신판매 신고, AI 이용 고지 같은 **책임을 코드에서 역추적**합니다.

## 3분 실행

```bash
cp .env.example .env   # GITHUB_TOKEN, OPENAI_API_KEY 기입
make up                # db + api + worker + caddy 기동
curl localhost/api/health
```

스캔 한 번:

```bash
curl -X POST localhost:8000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"repo_url": "https://github.com/<owner>/<repo>"}'
# → {"id": "...", "owner_token": "..."} (상세 조회용 영수증)
curl 'localhost:8000/api/scans/<id>?t=<owner_token>'
```

브라우저는 `http://localhost` → URL 입력 → 결과 화면 (`/scan?id=&t=`).

## 주요 기능 6가지

1. **원클릭 스캔** — 공개 GitHub URL 입력하면 preflight → 격리 클론 → 정적분석 → 점수까지 (소규모 리포 약 8초)
2. **건강 점수 0~100·A~F** — 보안 40 · 규제 40 · 라이선스 20, 테스트 코드는 접어서 미반영
3. **"이것만 고치면 +N점" 처방** — 같은 점수 산식의 결정적 계산, 고치고 `force` 재스캔하면 실제로 오름
4. **한국어 해설 (토글)** — 탐지는 정적분석만, LLM은 해설만. 끄면 점수·건수 불변으로 증명
5. **개인정보처리방침 초안** — 18목차 + 요약, 코드 신호로 자동 채움 (참고용, 법률 자문 아님)
6. **공개 목록·뱃지** — 동의한 스캔만 공개, `owner_token` 없이 상세 불가, 시크릿은 앞 2자만

## 규제 룰 (11개, `rules/`)

| 룰 | 신호 | 의무 |
|---|---|---|
| R1 | 위치 수집·위경도 컬럼 | 위치기반서비스사업 신고 |
| R2 | 개인정보 스키마·SDK | 처리방침 공개·적법 근거 |
| R3 | 토스·아임포트·Stripe | 통신판매업 신고 |
| R5 | 메일·SMS 발송 코드 | 광고성 정보 사전 동의 |
| R6 | OpenAI 등 생성형 AI 호출 | AI 산출물 표시·이용자 고지 |
| R7 | 주민번호 패턴·필드명 | 고유식별정보 처리 제한 |

조문 번호와 원문 링크만 제공합니다. **금액·형량 수치는 UI·문서 어디에도 쓰지 않습니다.**

## 스택

Python 3.12 · FastAPI · PostgreSQL 16 · gitleaks + semgrep(벤더링) ·
Next.js 14 static export · Caddy 2 · docker compose · GitHub Actions → ECR · EC2

```
브라우저 ─HTTPS─▶ Caddy ──▶ api:8000 ──▶ PostgreSQL ◀── worker (uid 10001, read-only, tmpfs)
```

## 문서

- 계획: [docs/PLAN.md](docs/PLAN.md) · 스펙: [docs/SPEC.md](docs/SPEC.md)
- 배포 절차: [docs/DEPLOY.md](docs/DEPLOY.md) · 기여: [CONTRIBUTING.md](CONTRIBUTING.md)

## 라이선스

MIT — [LICENSE](LICENSE)

## 고지

본 도구의 결과는 코드 분석 기반 참고용 진단이며 법률 자문이 아닙니다.
법령의 금액·형량·기간 수치는 표시하지 않으며, 최종 판단은 각 기관의 원문·지침으로 확인하세요.
