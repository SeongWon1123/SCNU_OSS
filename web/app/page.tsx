// Temporary landing (SPEC §8 hero). Real form wiring (/api/scans → /scan?id=&t=)
// lands with the API integration phase; the static shell below only proves the
// export build and the hero copy.
export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <section className="flex flex-col gap-3 text-center">
        <h1 className="text-2xl font-bold leading-snug tracking-tight">
          바이브코딩한 내 서비스, 배포해도 되나요?
        </h1>
        <p className="text-sm leading-relaxed text-neutral-400">
          GitHub 공개 저장소 주소만 넣으면 시크릿·규제·라이선스를 진단해 드립니다.
        </p>
      </section>
      <section className="flex flex-col gap-4">
        <input
          type="url"
          name="repo-url"
          placeholder="https://github.com/사용자/저장소"
          aria-label="진단할 GitHub 저장소 주소"
          className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-emerald-400"
        />
        <label className="flex items-start gap-2 text-xs leading-relaxed text-neutral-400">
          <input
            type="checkbox"
            name="consent"
            className="mt-0.5 accent-emerald-400"
          />
          진단 결과가 공개 목록에 표시되는 것에 동의해요.
        </label>
        <button
          type="button"
          disabled
          className="w-full rounded-md bg-emerald-400 px-3 py-2 text-sm font-semibold text-neutral-950 disabled:cursor-not-allowed disabled:opacity-40"
        >
          진단 시작하기 (곧 열릴 기능이에요)
        </button>
      </section>
    </main>
  );
}
