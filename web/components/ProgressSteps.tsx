// ProgressSteps — 9단계 진행 바 (preflight→clone→gitleaks→semgrep→manifest→scoring→explain→policy→upload).
'use client';

const STEPS: { key: string; label: string }[] = [
  { key: 'preflight', label: '사전 확인' },
  { key: 'clone', label: '저장소 복사' },
  { key: 'gitleaks', label: '시크릿 검사' },
  { key: 'semgrep', label: '규제 신호 검사' },
  { key: 'manifest', label: '매니페스트 분석' },
  { key: 'scoring', label: '점수 계산' },
  { key: 'explain', label: '해설 생성' },
  { key: 'policy', label: '문서 생성' },
  { key: 'upload', label: '업로드' },
];

const DONE_STEP = 'done';

export default function ProgressSteps({
  step,
  pct,
}: {
  step: string;
  pct: number;
}) {
  const index = step === DONE_STEP ? STEPS.length : Math.max(0, STEPS.findIndex((s) => s.key === step));

  return (
    <div data-testid="progress-steps" className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {STEPS.map((s, i) => {
          const done = i < index;
          const active = i === index;
          return (
            <li key={s.key} className="flex items-center gap-3">
              <span
                aria-hidden
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] ${
                  done
                    ? 'border-emerald-400 bg-emerald-400 text-neutral-950'
                    : active
                      ? 'border-emerald-400 text-emerald-400'
                      : 'border-neutral-700 text-neutral-600'
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span
                className={`text-sm ${done ? 'text-neutral-400' : active ? 'font-medium text-neutral-100' : 'text-neutral-600'}`}
              >
                {s.label}
              </span>
              {active && (
                <span className="ml-auto text-xs tabular-nums text-emerald-400">{pct}%</span>
              )}
            </li>
          );
        })}
      </ol>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-neutral-800"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(((index + Math.min(1, pct / 100)) / STEPS.length) * 100)}
      >
        <div
          className="h-full rounded-full bg-emerald-400 transition-all duration-500"
          style={{ width: `${Math.round(((index + Math.min(1, pct / 100)) / STEPS.length) * 100)}%` }}
        />
      </div>
    </div>
  );
}
