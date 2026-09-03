// EmptyState — done & findings 0: 100/A 카드 + "직접 확인할 6가지" 체크리스트.
'use client';

import ScoreCard from './ScoreCard';

const CHECKLIST = [
  { topic: '위치', question: '위치정보(GPS)를 수집하나요?' },
  { topic: '회원', question: '회원가입·로그인으로 개인정보를 저장하나요?' },
  { topic: '결제', question: '결제나 상품 판매 기능이 있나요?' },
  { topic: '메일', question: '이메일·알림을 발송하나요?' },
  { topic: 'AI', question: '생성형 AI 기능을 제공하나요?' },
  { topic: '미성년', question: '아동·청소년을 대상으로 하나요?' },
];

export default function EmptyState() {
  return (
    <section
      data-testid="empty-state"
      aria-label="탐지 결과 없음"
      className="flex flex-col gap-6"
    >
      <ScoreCard score={100} grade="A" scoreDetail={{ security: 40, regulation: 40, license: 20 }} />
      <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-5">
        <h2 className="text-base font-bold text-neutral-100">
          탐지 없음 ≠ 의무 없음 — 직접 확인할 6가지
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-neutral-400">
          코드에서 신호가 없었다는 뜻이지 법적 의무가 없다는 뜻은 아니에요. 아래 항목을 직접 확인해 보세요.
        </p>
        <ul className="mt-4 flex flex-col gap-2.5">
          {CHECKLIST.map(({ topic, question }) => (
            <li key={topic} className="flex items-start gap-2.5 text-sm text-neutral-300">
              <input
                type="checkbox"
                aria-label={`${topic} 확인`}
                className="mt-1 h-4 w-4 shrink-0 accent-emerald-400"
              />
              <span>
                <span className="mr-2 rounded bg-neutral-800 px-1.5 py-0.5 text-xs font-semibold text-emerald-400">
                  {topic}
                </span>
                {question}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
