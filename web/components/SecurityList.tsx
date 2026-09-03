// SecurityList — 보안 탭: 시크릿 마스킹 스니펫 (서버가 앞 2자+**** 마스킹한 값을 그대로 표시).
'use client';

import { severityColor } from '@/lib/tokens';
import type { Finding } from '@/lib/types';

export default function SecurityList({
  findings,
  revealed,
}: {
  findings: Finding[];
  revealed: boolean;
}) {
  if (findings.length === 0) {
    return (
      <p data-testid="security-list" className="rounded-md border border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400">
        시크릿 유출 신호가 없어요.
      </p>
    );
  }

  return (
    <ul data-testid="security-list" className="flex flex-col gap-3">
      {findings.map((f) => (
        <li key={f.id} className="flex flex-col gap-2 rounded-md border border-neutral-800 bg-neutral-900/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-neutral-950"
              style={{ backgroundColor: severityColor(f.severity) }}
            >
              {f.severity}
            </span>
            <code className="text-xs text-neutral-500">{f.rule_id}</code>
            {f.file_path && (
              <code className="text-xs text-neutral-400">
                {f.file_path}
                {f.line_start != null && `:${f.line_start}`}
              </code>
            )}
          </div>
          <p className="text-sm font-medium text-neutral-100">{f.title_ko}</p>
          {f.snippet && (
            <pre className="overflow-x-auto rounded bg-neutral-950/80 p-2 text-xs leading-relaxed text-neutral-300">
              <code data-testid="masked-snippet">{f.snippet}</code>
            </pre>
          )}
          {revealed && f.explain_ko && (
            <p className="text-sm leading-relaxed text-neutral-300">{f.explain_ko}</p>
          )}
          {revealed && f.fix_ko && (
            <p className="text-sm leading-relaxed text-neutral-300">{f.fix_ko}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
