// LlmPanel — meta.llm 표시 + 해설 끄기 토글 (OFF 시 explain_ko/fix_ko 숨김, 점수·건수 불변).
'use client';

import type { LlmMeta } from '@/lib/types';

const STATUS_LABELS: Record<string, string> = {
  ok: '해설 완료',
  skipped: '해설 생략 (LLM 키 미설정 또는 확인 실패)',
  explain_off: '해설 끄기 요청 스캔',
};

export default function LlmPanel({
  llm,
  revealed,
  onToggle,
}: {
  llm: LlmMeta | undefined;
  revealed: boolean;
  onToggle: () => void;
}) {
  return (
    <section
      data-testid="llm-panel"
      aria-label="AI 해설 정보"
      className="flex flex-col gap-3 rounded-md border border-neutral-800 bg-neutral-900/60 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-neutral-300">AI 해설</h2>
        <button
          type="button"
          data-testid="llm-toggle"
          onClick={onToggle}
          aria-pressed={!revealed}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-300 hover:border-neutral-500 hover:text-neutral-100"
        >
          {revealed ? '해설 끄기' : '해설 켜기'}
        </button>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-neutral-400">
        <div className="flex gap-1.5">
          <dt>상태</dt>
          <dd data-testid="llm-status" className="text-neutral-200">
            {llm ? (STATUS_LABELS[llm.status] ?? llm.status) : '해설 정보 없음'}
          </dd>
        </div>
        {llm && (
          <>
            <div className="flex gap-1.5">
              <dt>모델</dt>
              <dd className="text-neutral-200">{llm.model || '미설정'}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>호출</dt>
              <dd className="tabular-nums text-neutral-200">{llm.calls}회</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>해설</dt>
              <dd className="tabular-nums text-neutral-200">{llm.explained}건</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>검증 폐기</dt>
              <dd className="tabular-nums text-neutral-200">
                인용 {llm.dropped_by_citation}건 · 번호 {llm.dropped_by_number}건
              </dd>
            </div>
          </>
        )}
      </dl>
      {!revealed && (
        <p className="text-xs leading-relaxed text-amber-300/90">
          해설이 꺼져 있어요. 룰 기본 정보(제목·코드 조각)만 표시되며 점수와 건수는 변하지 않아요.
        </p>
      )}
    </section>
  );
}
