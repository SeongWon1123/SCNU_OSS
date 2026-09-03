// LicenseList — 라이선스 탭: 라이선스 축 findings 목록.
'use client';

import type { Finding } from '@/lib/types';

export default function LicenseList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return (
      <p data-testid="license-list" className="rounded-md border border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400">
        확인이 필요한 라이선스 신호가 없어요.
      </p>
    );
  }

  return (
    <ul data-testid="license-list" className="flex flex-col gap-3">
      {findings.map((f) => (
        <li key={f.id} className="flex flex-col gap-1.5 rounded-md border border-neutral-800 bg-neutral-900/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
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
            <pre className="overflow-x-auto rounded bg-neutral-950/80 p-2 text-xs leading-relaxed text-neutral-400">
              <code>{f.snippet}</code>
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}
