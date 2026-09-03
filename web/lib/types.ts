// API response types — mirrors api/app/schemas.py + routers/scans.py actual shapes (SPEC §4.2).

export type ScanStatus = 'queued' | 'running' | 'done' | 'failed' | 'rejected';

/** POST /api/scans 201 (새 스캔 — owner_token 포함) */
export interface ScanCreated {
  id: string;
  status: ScanStatus;
  owner_token: string;
  queue_position: number;
}

/** POST /api/scans 200 (24시간 캐시 적중 — token 없음, 점수만 열람) */
export interface ScanCached {
  id: string;
  status: ScanStatus;
  queue_position: number;
}

export type ScanCreateResponse = ScanCreated | ScanCached;

export interface Finding {
  id: number;
  scan_id: string;
  axis: 'security' | 'regulation' | 'license' | (string & {});
  scope: string; // 'app' | 'test' | 'sample' — 점수 반영은 app만
  rule_id: string;
  reg_rule: string | null; // R1·R2·R3·R5·R6·R7
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info' | (string & {});
  confidence: string | null; // high|medium|low
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  snippet: string | null; // 시크릿은 앞 2자 + **** 마스킹
  title_ko: string;
  explain_ko: string | null;
  fix_ko: string | null;
  weight: number;
}

/** meta.progress — pipeline이 단계마다 갱신 */
export interface ProgressInfo {
  step: string; // preflight → clone → gitleaks → semgrep → manifest → scoring → explain → policy → upload → done
  pct: number;
  counts: {
    secrets?: number;
    regulation?: number;
    security?: number;
  } | null;
}

/** meta.llm — explain 단계 결과 (키 미설정 시 status 'skipped'/'explain_off'가 정상) */
export interface LlmMeta {
  model: string;
  calls: number;
  status: string; // ok | skipped | explain_off
  explained: number;
  dropped_by_citation: number;
  dropped_by_number: number;
}

export interface ScanMeta {
  explain?: boolean;
  queue_position?: number;
  progress?: ProgressInfo;
  counts?: ProgressInfo['counts'];
  llm?: LlmMeta;
  stripped_files?: number; // 리포의 스캔 제외 설정 무시 안내용
  tools?: Record<string, string>;
  timings?: Record<string, number>;
}

/** GET /api/scans/{id}?t= — 토큰 일치 시 전체 응답 */
export interface ScanFull {
  id: string;
  repo_url: string;
  owner: string;
  repo: string;
  consent: boolean;
  commit_sha: string | null;
  default_branch: string | null;
  status: ScanStatus;
  error: string | null;
  score: number | null;
  grade: string | null;
  score_detail: AxisDetail | null;
  summary_ko: string | null;
  privacy_policy_md: string | null;
  ai_notice_md: string | null;
  meta: ScanMeta;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  findings: Finding[];
}

/** 3축 잔여 예산 (§6:233 — detail = 잔여) */
export interface AxisDetail {
  security?: number;
  regulation?: number;
  license?: number;
}

/** GET /api/scans/{id}?t= — 불일치/없음 시 축약 응답 (running이면 findings가 붙을 수 있음) */
export interface ScanLimited {
  id: string;
  status: ScanStatus;
  score: number | null;
  grade: string | null;
  score_detail: AxisDetail | null;
  progress: ProgressInfo | null;
  message: string;
  findings?: Finding[];
}

export type ScanDetail = ScanFull | ScanLimited;

export function isScanFull(scan: ScanDetail): scan is ScanFull {
  return 'repo_url' in scan;
}

/** GET /api/scans/recent — consent=true & done 최근 3개 */
export interface RecentScan {
  owner: string;
  repo: string;
  score: number | null;
  grade: string | null;
}

/** GET /api/health */
export interface HealthStatus {
  ok: boolean;
  db: boolean;
  worker_seen_at: string | null;
}

/** GET /api/stats */
export interface Stats {
  scans_done: number;
  repos: number;
  last_24h: number;
}
