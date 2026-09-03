// fetch wrappers — NEXT_PUBLIC_API_BASE=/api (같은 오리진, SPEC §8).
// 422/429 등 에러는 서버 detail(한국어)을 그대로 노출한다.

import type {
  RecentScan,
  ScanCreateResponse,
  ScanDetail,
  Stats,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없어요. 잠시 후 다시 시도하세요');
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail.length > 0) {
      return body.detail; // 서버 한국어 메시지 그대로
    }
  } catch {
    // body 파싱 실패 시 아래 기본 문구 사용
  }
  if (response.status === 422) {
    return '공개 GitHub 저장소 주소만 지원해요 (예: https://github.com/소유자/저장소)';
  }
  if (response.status === 429) {
    return '오늘 스캔 요청 한도에 도달했어요 — 내일 다시 시도하세요';
  }
  if (response.status === 404) {
    return '스캔을 찾을 수 없어요';
  }
  return '요청을 처리하지 못했어요. 잠시 후 다시 시도하세요';
}

export function createScan(
  repoUrl: string,
  consent: boolean,
  force = false,
): Promise<ScanCreateResponse> {
  return request<ScanCreateResponse>('/scans', {
    method: 'POST',
    body: JSON.stringify({ repo_url: repoUrl, consent, force }),
  });
}

export async function getScan(id: string, token = ''): Promise<ScanDetail> {
  const query = token ? `?t=${encodeURIComponent(token)}` : '';
  return request<ScanDetail>(`/scans/${encodeURIComponent(id)}${query}`);
}

export function getRecent(): Promise<RecentScan[]> {
  return request<RecentScan[]>('/scans/recent');
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/stats');
}

/** 방침/AI 고지 다운로드 — 브라우저 다운로드로 이어진다. */
export async function downloadPolicy(id: string, token: string): Promise<void> {
  await downloadMarkdown(`/scans/${encodeURIComponent(id)}/privacy-policy.md?t=${encodeURIComponent(token)}`, '개인정보처리방침-초안.md');
}

export async function downloadAiNotice(id: string, token: string): Promise<void> {
  await downloadMarkdown(`/scans/${encodeURIComponent(id)}/ai-notice.md?t=${encodeURIComponent(token)}`, 'AI-이용-고지.md');
}

async function downloadMarkdown(path: string, filename: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없어요. 잠시 후 다시 시도하세요');
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/**
 * 2초 폴링 — status가 queued/running인 동안 onTick을 반복 호출한다.
 * 반환값: 폴링 중단 함수 (unmount 시 호출).
 */
export function pollScan(
  id: string,
  token: string,
  onTick: (scan: ScanDetail | null, error: Error | null) => void,
  intervalMs = 2000,
): () => void {
  let timer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;

  const tick = async () => {
    if (stopped) {
      return;
    }
    try {
      const scan = await getScan(id, token);
      onTick(scan, null);
      if (scan.status !== 'queued' && scan.status !== 'running') {
        stop();
      }
    } catch (error) {
      onTick(null, error instanceof Error ? error : new ApiError(0, '알 수 없는 오류'));
    }
  };

  const stop = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  void tick();
  timer = setInterval(() => void tick(), intervalMs);

  return () => {
    stopped = true;
    stop();
  };
}
