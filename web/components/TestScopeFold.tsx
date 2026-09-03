// TestScopeFold — 테스트·샘플 코드 findings 접기 (점수 미반영 안내).
'use client';

import { useState } from 'react';
import type { Finding } from '@/lib/types';

export default function TestScopeFold({ findings }: { findings: Finding[] }) {
  const [open, setOpen] = useState(false);
  if (findings.length === 0) {
    return null;
  }

  return (
    <section
      data-testid="test-scope-fold"
      className="rounded-md border border-neutral-800 bg-neutral-900/40"
    >
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 p-4 text-left"
      >
        <span className="text-sm text-neutral-300">
          테스트·샘플 코드 {findings.length}건 — <span className="text-neutral-500">점수 미반영</span>
        </span>
        <span aria-hidden className="text-xs text-neutral-500">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <ul className="flex flex-col gap-2 px-4 pb-4">
          {findings.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
              <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-300">{f.scope}</span>
              <code className="text-neutral-500">{f.rule_id}</code>
              {f.file_path && (
                <code>
                  {f.file_path}
                  {f.line_start != null && `:${f.line_start}`}
                </code>
              )}
              <span>{f.title_ko}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
