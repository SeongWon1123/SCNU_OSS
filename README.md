# 리포닥 (RepoDoc)

> GitHub 공개 저장소 URL 하나로 보안·라이선스·한국 규제 준수를 진단하는 오픈소스 클리닉.
> 2026 SCNU OSS·AI 해커톤 고급 트랙 출품작 — 개발 진행 중.

## 문서
- 계획: [docs/PLAN.md](docs/PLAN.md)
- 스펙: [docs/SPEC.md](docs/SPEC.md)
- 에이전트 프롬프트: [docs/PROMPTS.md](docs/PROMPTS.md)
- 규칙: [AGENTS.md](AGENTS.md)

## 로컬 실행 (Phase 0 완료 후)
```
cp .env.example .env
make up
curl localhost/api/health
```
