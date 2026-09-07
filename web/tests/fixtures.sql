-- web e2e fixtures (e2e.spec.ts). Idempotent: delete-then-insert by fixed UUIDs.
-- Run AFTER pytest (conftest truncates tables).

DELETE FROM findings WHERE scan_id IN (
  '11111111-1111-1111-1111-111111111111',
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333');
DELETE FROM scans WHERE id IN (
  '11111111-1111-1111-1111-111111111111',
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333');

-- a: done 60/C, consent=true, 3 findings (R1 + gitleaks + license)
INSERT INTO scans (id, repo_url, owner, repo, owner_token, consent,
  commit_sha, default_branch, status, error, score, grade,
  score_detail, summary_ko, privacy_policy_md, ai_notice_md, meta,
  created_at, started_at, finished_at)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'https://github.com/octocat/fixture-a', 'octocat', 'fixture-a', 'tok-a-repodoc-e2e', true,
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'main', 'done', NULL, 60, 'C',
  '{"security": 25, "regulation": 32, "license": 10}',
  '진단 점수는 60점(C등급)입니다.',
  NULL, NULL,
  '{"explain": true, "queue_position": 0, "progress": {"step": "done", "pct": 100, "counts": {"secrets": 1, "regulation": 1, "security": 1}}, "llm": {"model": "", "calls": 0, "status": "skipped", "explained": 0, "dropped_by_citation": 0, "dropped_by_number": 0}, "timings": {"preflight": 1.0}}',
  now(), now(), now()
);

INSERT INTO findings (scan_id, axis, scope, rule_id, reg_rule, severity, confidence,
  file_path, line_start, line_end, snippet, title_ko, explain_ko, fix_ko, weight)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'regulation', 'app',
   'semgrep:kr-r1-browser-geolocation', 'R1', 'medium', 'medium',
   'src/map.js', 3, 5, 'navigator.geolocation',
   '브라우저 위치정보를 수집합니다',
   '브라우저 위치 API를 서버와 연동하면 신고 대상일 수 있습니다.',
   '좌표 저장 전에 신고 여부를 확인하세요.', 8),
  ('11111111-1111-1111-1111-111111111111', 'security', 'app',
   'gitleaks:generic-api-key', NULL, 'critical', NULL,
   'config.js', 1, 1, 'AK****',
   '시크릿이 커밋된 것으로 보입니다', NULL, NULL, 15),
  ('11111111-1111-1111-1111-111111111111', 'license', 'app',
   'license:some-lib', NULL, 'high', NULL,
   'package.json', 11, 11, 'GPL-3.0',
   '카피레프트 라이선스 패키지가 사용되고 있습니다', NULL, NULL, 10);

-- b: queued, queue_position 2
INSERT INTO scans (id, repo_url, owner, repo, owner_token, consent,
  status, score, grade, meta, created_at)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  'https://github.com/octocat/fixture-b', 'octocat', 'fixture-b', 'tok-b-repodoc-e2e', false,
  'queued', NULL, NULL,
  '{"explain": true, "queue_position": 2, "progress": {"step": "clone", "pct": 20, "counts": null}}',
  now()
);

-- c: done 100/A, findings 0, consent=false
INSERT INTO scans (id, repo_url, owner, repo, owner_token, consent,
  commit_sha, default_branch, status, error, score, grade,
  score_detail, summary_ko, meta, created_at, started_at, finished_at)
VALUES (
  '33333333-3333-3333-3333-333333333333',
  'https://github.com/octocat/fixture-c', 'octocat', 'fixture-c', 'tok-c-repodoc-e2e', false,
  'cccccccccccccccccccccccccccccccccccccccc', 'main', 'done', NULL, 100, 'A',
  '{"security": 40, "regulation": 40, "license": 20}',
  '발견된 보안·규제 항목이 없습니다.',
  '{"explain": true, "queue_position": 0, "progress": {"step": "done", "pct": 100}}',
  now(), now(), now()
);
