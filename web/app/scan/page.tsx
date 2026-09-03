'use client';

// /scan?id=&t= — 쿼리스트링 라우트 ([id] 동적 세그먼트 금지, SPEC §8).
// 상태 머신: queued/running → 로딩(ProgressSteps·대기 순번·counts·60초 안내·2초 폴링)
//   done + findings 0 → EmptyState | done → 결과 | failed/rejected → ErrorState(force 재시도)
//   토큰 불일치 → 점수·등급·3축만 | 존재하지 않는 id → ErrorState.

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ApiError,
  createScan,
  downloadAiNotice,
  downloadPolicy,
  pollScan,
} from '@/lib/api';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import LicenseList from '@/components/LicenseList';
import LlmPanel from '@/components/LlmPanel';
import ProgressSteps from '@/components/ProgressSteps';
import RegCard from '@/components/RegCard';
import ScoreCard from '@/components/ScoreCard';
import SecurityList from '@/components/SecurityList';
import TestScopeFold from '@/components/TestScopeFold';
import { isScanFull, type Finding, type ScanDetail } from '@/lib/types';

const SLOW_SCAN_AFTER_SECONDS = 60;
const SLOW_SCAN_NOTICE = '보통 90초, 대형 리포는 더 걸립니다';
const TOP_NOTICE = '본 결과는 코드 분석 기반 참고용 진단이며 법률 자문이 아닙니다';

type TabKey = 'regulation' | 'security' | 'license';

function countsLine(scan: ScanDetail): string | null {
  const counts =
    (isScanFull(scan) ? scan.meta.progress?.counts : scan.progress?.counts) ??
    (isScanFull(scan) ? scan.meta.counts : undefined);
  if (!counts) {
    return null;
  }
  const parts: string[] = [];
  if (counts.secrets) {
    parts.push(`시크릿 ${counts.secrets}건`);
  }
  if (counts.regulation) {
    parts.push(`규제 신호 ${counts.regulation}건`);
  }
  if (counts.security) {
    parts.push(`보안 신호 ${counts.security}건`);
  }
  return parts.length > 0 ? `${parts.join(' · ')} 발견...` : null;
}

function groupByRegRule(findings: Finding[]): [string, Finding[]][] {
  const groups = new Map<string, Finding[]>();
  for (const finding of findings) {
    if (!finding.reg_rule) {
      continue;
    }
    groups.set(finding.reg_rule, [...(groups.get(finding.reg_rule) ?? []), finding]);
  }
  return Array.from(groups.entries()).sort(
    ([, a], [, b]) =>
      b.reduce((sum, f) => sum + f.weight, 0) - a.reduce((sum, f) => sum + f.weight, 0),
  );
}

function ScanView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = searchParams.get('id');
  const token = searchParams.get('t') ?? '';

  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [revealed, setRevealed] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('regulation');
  const [retrying, setRetrying] = useState(false);
  const startedAtRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!id) {
      setError('요청 정보가 없어요. 랜딩에서 다시 시작해 주세요');
      return;
    }
    setScan(null);
    setError(null);
    setElapsed(0);
    setActiveTab('regulation');
    startedAtRef.current = Date.now();
    return pollScan(id, token, (next, err) => {
      if (err) {
        setError(err instanceof ApiError ? err.message : '스캔 정보를 불러오지 못했어요');
        return;
      }
      setScan(next);
    });
  }, [id, token]);

  useEffect(() => {
    const pending = scan && (scan.status === 'queued' || scan.status === 'running');
    if (!pending) {
      return;
    }
    const timer = setInterval(() => {
      setElapsed(Math.round((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [scan]);

  const retry = useCallback(async () => {
    if (!id || !scan || !isScanFull(scan)) {
      return;
    }
    setRetrying(true);
    try {
      const created = await createScan(scan.repo_url, scan.consent, true);
      const tokenParam = 'owner_token' in created ? created.owner_token : '';
      router.push(
        `/scan?id=${encodeURIComponent(created.id)}&t=${encodeURIComponent(tokenParam)}`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '다시 요청하지 못했어요');
      setRetrying(false);
    }
  }, [id, scan, router]);

  if (!id || (error && !scan)) {
    return (
      <Shell>
        <ErrorState message={error ?? '요청 정보가 없어요'} />
      </Shell>
    );
  }

  if (!scan) {
    return (
      <Shell>
        <p data-testid="scan-loading" className="text-sm text-neutral-400">
          불러오는 중이에요...
        </p>
      </Shell>
    );
  }

  if (!isScanFull(scan)) {
    // 토큰 불일치 — 점수·등급·3축만 (SPEC §8 마지막 행).
    return (
      <Shell>
        <div className="flex flex-col gap-4">
          <p
            data-testid="limited-notice"
            className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3 text-center text-xs text-neutral-400"
          >
            {scan.message}
          </p>
          <ScoreCard
            score={scan.score}
            grade={scan.grade}
            scoreDetail={scan.score_detail}
          />
        </div>
      </Shell>
    );
  }

  if (scan.status === 'failed' || scan.status === 'rejected') {
    return (
      <Shell>
        <ErrorState
          message={scan.error ?? '진단을 마치지 못했어요'}
          onRetry={() => void retry()}
          retrying={retrying}
        />
      </Shell>
    );
  }

  if (scan.status === 'queued' || scan.status === 'running') {
    const progress = scan.meta.progress;
    const queuePosition = scan.meta.queue_position ?? 0;
    const line = countsLine(scan);
    return (
      <Shell>
        <div data-testid="scan-progress" className="flex flex-col gap-6">
          <header className="flex flex-col gap-1 text-center">
            <h1 className="text-lg font-bold">진단을 진행하고 있어요</h1>
            <p className="text-xs text-neutral-400">{scan.repo_url}</p>
          </header>
          {queuePosition > 0 && (
            <p data-testid="queue-position" className="text-center text-sm text-emerald-400">
              대기 순번 {queuePosition}번
            </p>
          )}
          <ProgressSteps step={progress?.step ?? 'preflight'} pct={progress?.pct ?? 0} />
          {line && (
            <p data-testid="counts-line" className="text-center text-sm text-neutral-300">
              {line}
            </p>
          )}
          {elapsed >= SLOW_SCAN_AFTER_SECONDS && (
            <p data-testid="slow-notice" className="text-center text-xs text-amber-300/90">
              {SLOW_SCAN_NOTICE}
            </p>
          )}
        </div>
      </Shell>
    );
  }

  // done
  if (scan.findings.length === 0) {
    return (
      <Shell>
        <EmptyState />
      </Shell>
    );
  }

  const appFindings = scan.findings.filter((f) => f.scope === 'app');
  const testFindings = scan.findings.filter((f) => f.scope !== 'app');
  const regulationGroups = groupByRegRule(appFindings.filter((f) => f.axis === 'regulation'));
  const securityFindings = appFindings.filter((f) => f.axis === 'security');
  const licenseFindings = appFindings.filter((f) => f.axis === 'license');
  const tabCounts: Record<TabKey, number> = {
    regulation: regulationGroups.length,
    security: securityFindings.length,
    license: licenseFindings.length,
  };
  const tabLabels: Record<TabKey, string> = {
    regulation: '규제',
    security: '보안',
    license: '라이선스',
  };
  const tabTestIds: Record<TabKey, string> = {
    regulation: 'reg-tab',
    security: 'security-tab',
    license: 'license-tab',
  };

  return (
    <Shell>
      <div className="flex flex-col gap-5">
        <p className="sticky top-0 z-10 -mx-6 border-b border-neutral-800 bg-neutral-950/95 px-6 py-2.5 text-center text-xs leading-relaxed text-neutral-400 backdrop-blur">
          {TOP_NOTICE}
        </p>

        <header className="flex flex-col gap-1">
          <h1 className="text-lg font-bold">
            {scan.owner}/{scan.repo}
          </h1>
          <p data-testid="summary" className="text-sm leading-relaxed text-neutral-400">
            {scan.summary_ko ?? '진단이 끝났어요.'}
          </p>
        </header>

        <ScoreCard score={scan.score} grade={scan.grade} scoreDetail={scan.score_detail} />

        <LlmPanel
          llm={scan.meta.llm}
          revealed={revealed}
          onToggle={() => setRevealed((prev) => !prev)}
        />

        {(scan.meta.stripped_files ?? 0) > 0 && (
          <p data-testid="stripped-notice" className="rounded-md border border-amber-700/50 bg-amber-950/20 p-3 text-xs leading-relaxed text-amber-300">
            리포의 스캔 제외 설정은 무시됨 — .gitignore 등 제외 규칙을 적용하지 않고 {scan.meta.stripped_files}개 파일을 검사했어요.
          </p>
        )}

        <div className="flex gap-2" role="tablist" aria-label="진단 결과 분류">
          {(Object.keys(tabLabels) as TabKey[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeTab === key}
              data-testid={tabTestIds[key]}
              onClick={() => setActiveTab(key)}
              className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${
                activeTab === key
                  ? 'border-emerald-400 bg-emerald-400/10 text-emerald-400'
                  : 'border-neutral-800 text-neutral-400 hover:border-neutral-600 hover:text-neutral-200'
              }`}
            >
              {tabLabels[key]} {tabCounts[key]}
            </button>
          ))}
        </div>

        <div role="tabpanel" aria-label={`${tabLabels[activeTab]} 결과`} className="flex flex-col gap-3">
          {activeTab === 'regulation' &&
            (regulationGroups.length === 0 ? (
              <p className="rounded-md border border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400">
                규제 신호가 없어요.
              </p>
            ) : (
              regulationGroups.map(([rule, findings]) => (
                <RegCard key={rule} regRule={rule} findings={findings} revealed={revealed} />
              ))
            ))}
          {activeTab === 'security' && <SecurityList findings={securityFindings} revealed={revealed} />}
          {activeTab === 'license' && <LicenseList findings={licenseFindings} />}
        </div>

        <TestScopeFold findings={testFindings} />

        <div className="flex flex-col gap-2 sm:flex-row">
          {scan.privacy_policy_md && (
            <button
              type="button"
              data-testid="download-policy"
              onClick={() => void downloadPolicy(scan.id, token)}
              className="flex-1 rounded-md border border-neutral-700 px-3 py-2.5 text-sm font-medium text-neutral-200 hover:border-emerald-400 hover:text-emerald-400"
            >
              개인정보처리방침 초안 내려받기
            </button>
          )}
          {scan.ai_notice_md && (
            <button
              type="button"
              data-testid="download-ai-notice"
              onClick={() => void downloadAiNotice(scan.id, token)}
              className="flex-1 rounded-md border border-neutral-700 px-3 py-2.5 text-sm font-medium text-neutral-200 hover:border-emerald-400 hover:text-emerald-400"
            >
              AI 이용 고지 내려받기
            </button>
          )}
        </div>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-6 py-8">
      {children}
    </main>
  );
}

export default function ScanPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-dvh w-full max-w-md items-center justify-center px-6">
          <p className="text-sm text-neutral-400">불러오는 중이에요...</p>
        </main>
      }
    >
      <ScanView />
    </Suspense>
  );
}
