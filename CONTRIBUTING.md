# 기여 안내 (CONTRIBUTING)

리포닥에 기여해 주셔서 감사합니다. 이 문서는 기여 절차와 규칙을 안내합니다.

## 로컬 개발 시작하기

```bash
cp .env.example .env
make up
curl localhost/api/health   # {"ok":true,"db":true,"worker_seen_at":null} 이면 정상
```

모든 실행은 `docker compose` 안에서 이루어집니다. 호스트에 semgrep/gitleaks를 직접 설치하지 않습니다.

| 명령 | 하는 일 |
|---|---|
| `make up` | db·api·worker·caddy 기동 |
| `make test` | 컨테이너 안에서 pytest 실행 |
| `make lint` | 컨테이너 안에서 ruff 실행 |
| `make build-web` | caddy 이미지 로컬 빌드 |
| `make down` | 전체 중지 |

## 규칙(룰) 기여 절차

한국 규제 커스텀 룰(`rules/kr-regulation.yaml`)은 **사람 B만 직접 수정**합니다.
제안은 다음 절차로 합니다.

1. `.github/ISSUE_TEMPLATE/rule.md` 양식으로 이슈를 등록합니다 — 신호·의무·조문 링크·sample/positive 케이스·negative 케이스를 전부 채워주세요.
2. 유지관리자(사람 B)가 신호의 정합성과 오발 위험을 검토합니다.
3. 승인되면 사람 B가 규칙과 sample 케이스를 반영하고, `api/tests/test_semgrep_rules.py`로 회귀를 잠급니다.
4. 주의: 법령의 금액·형량·기간 수치는 코드·문자열·주석·문서·테스트 어디에도 쓰지 않습니다. 수치는 `rules/catalog.yaml`의 문자열만 사용합니다.

## 테스트

PR은 `make test`(컨테이너 안 pytest)와 `make lint`를 통과해야 합니다.
`api/tests/**`의 삭제 줄 수가 추가 줄 수보다 많으면 CI 가드가 실패합니다 — 테스트를 삭제하거나 완화하지 않습니다.

## PR 계약

PR 본문은 `.github/PULL_REQUEST_TEMPLATE.md`의 6개 항목을 그대로 채웁니다:

1. 참조한 SPEC §
2. 실행한 명령과 실제 출력
3. 변경 파일 목록 · 잠금 파일 미접촉 선언
4. 새 의존성과 이유
5. 테스트 추가/변경/삭제 수 (감소 시 사유)
6. 스펙과 다르게 구현한 점과 이유

PR은 **400줄·12파일 이하**입니다. 잠금 파일(`api/app/db.py`, `api/app/models.py`, `api/worker/pipeline.py`, `rules/**`, `docs/LAW_REFERENCES.md`, `api/tests/test_semgrep_rules.py`, `.github/workflows/ci.yml`)을 건드리려면 `unlock-approved` 라벨이 필요하고, 사람 B 전용 파일은 사람 B의 커밋만 허용됩니다.