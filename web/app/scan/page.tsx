'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

// Query-string route: /scan?id=&t= (SPEC §8 — `[id]` dynamic segment is forbidden).
// useSearchParams() must stay inside <Suspense> or the static export build fails.
function ScanProgress() {
  const searchParams = useSearchParams();
  const scanId = searchParams.get('id');

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-4 px-6 py-12 text-center">
      <h1 className="text-xl font-bold">스캔을 준비하고 있어요.</h1>
      <p className="text-sm leading-relaxed text-neutral-400">
        저장소를 살펴보고 진단 리포트를 만들고 있어요. 보통 90초 정도 걸려요.
      </p>
      <p className="text-xs text-neutral-500">
        {scanId ? `요청 번호 ${scanId}` : '요청 정보가 없어요.'}
      </p>
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
      <ScanProgress />
    </Suspense>
  );
}
