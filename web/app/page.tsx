'use client';

// 랜딩 — SPEC §8: 히어로 · URL 입력 · consent 체크 · 제출 → /scan?id=&t=
// stats 임계 10 · recent 3개 · 422/429 한국어 에러 인라인.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError, createScan, getRecent, getStats } from '@/lib/api';
import { gradeColor } from '@/lib/tokens';
import type { RecentScan, Stats } from '@/lib/types';

const STATS_TEAM_THRESHOLD = 10;

export default function HomePage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<RecentScan[]>([]);
  const [repoUrl, setRepoUrl] = useState('');
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => setStats(null));
    getRecent()
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const created = await createScan(repoUrl.trim(), consent);
      const token = 'owner_token' in created ? `&t=${encodeURIComponent(created.owner_token)}` : '';
      router.push(`/scan?id=${encodeURIComponent(created.id)}${token}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '요청을 처리하지 못했어요. 잠시 후 다시 시도하세요');
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-10 px-6 py-12">
      <section className="flex flex-col gap-3 text-center">
        <h1 className="text-2xl font-bold leading-snug tracking-tight">
          바이브코딩한 내 서비스, 배포해도 되나요?
        </h1>
        <p className="text-sm leading-relaxed text-neutral-400">
          GitHub 공개 저장소 주소만 넣으면 시크릿·규제·라이선스를 진단해 드립니다.
        </p>
        {stats && (
          <p data-testid="stats-line" className="text-xs font-medium text-emerald-400">
            {stats.scans_done >= STATS_TEAM_THRESHOLD
              ? `이번 대회 ${stats.repos}팀 진단`
              : `스캔 ${stats.scans_done}회`}
          </p>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <input
          type="url"
          data-testid="repo-url"
          value={repoUrl}
          onChange={(event) => setRepoUrl(event.target.value)}
          placeholder="https://github.com/사용자/저장소"
          aria-label="진단할 GitHub 저장소 주소"
          className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2.5 text-sm placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-emerald-400"
        />
        <label className="flex items-start gap-2 text-xs leading-relaxed text-neutral-400">
          <input
            type="checkbox"
            data-testid="consent"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            className="mt-0.5 h-4 w-4 accent-emerald-400"
          />
          공개 목록에 표시 동의
        </label>
        <button
          type="button"
          data-testid="submit"
          onClick={() => void submit()}
          disabled={submitting || repoUrl.trim().length === 0}
          className="w-full rounded-md bg-emerald-400 px-3 py-2.5 text-sm font-semibold text-neutral-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? '요청하는 중...' : '진단 시작하기'}
        </button>
        {error && (
          <p data-testid="form-error" role="alert" className="text-xs leading-relaxed text-red-400">
            {error}
          </p>
        )}
      </section>

      {recent.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-neutral-300">최근 진단</h2>
          <ul data-testid="recent-list" className="flex flex-col gap-2">
            {recent.map((scan) => (
              <li
                key={`${scan.owner}/${scan.repo}`}
                className="flex items-center gap-3 rounded-md border border-neutral-800 bg-neutral-900/60 px-4 py-3"
              >
                <span className="truncate text-sm text-neutral-200">
                  {scan.owner}/{scan.repo}
                </span>
                <span
                  className="ml-auto shrink-0 text-sm font-bold tabular-nums"
                  style={{ color: gradeColor(scan.grade) }}
                >
                  {scan.score ?? '-'} · {scan.grade ?? '?'}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
