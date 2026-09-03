// ErrorState — failed/rejected/존재하지 않는 id: 사유 + 재시도(force) 버튼.
'use client';

export default function ErrorState({
  message,
  onRetry,
  retrying,
}: {
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  return (
    <section
      data-testid="error-state"
      role="alert"
      aria-label="진단 실패"
      className="flex flex-col items-center gap-4 rounded-md border border-red-900/50 bg-red-950/20 p-8 text-center"
    >
      <span aria-hidden className="text-3xl">⚠️</span>
      <h2 className="text-base font-bold text-neutral-100">진단을 마치지 못했어요</h2>
      <p data-testid="error-reason" className="text-sm leading-relaxed text-neutral-300">
        {message}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="rounded-md bg-emerald-400 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {retrying ? '다시 요청하는 중...' : '다시 진단하기'}
        </button>
      )}
      {onRetry && (
        <p className="text-xs text-neutral-500">
          하루 스캔 요청 한도는 IP당 100회예요.
        </p>
      )}
    </section>
  );
}
