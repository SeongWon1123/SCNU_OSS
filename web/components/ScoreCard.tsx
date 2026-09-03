// ScoreCard — SVG 원형 게이지 + 3축 바. 차트 라이브러리 없이 순수 SVG (SPEC §8).
'use client';

import {
  AXIS_CAPS,
  AXIS_LABELS,
  type AxisKey,
  gradeColor,
} from '@/lib/tokens';
import type { AxisDetail } from '@/lib/types';

const RADIUS = 64;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function ScoreCard({
  score,
  grade,
  scoreDetail,
}: {
  score: number | null;
  grade: string | null;
  scoreDetail: AxisDetail | null;
}) {
  const color = gradeColor(grade);
  const clamped = Math.max(0, Math.min(100, score ?? 0));
  const offset = CIRCUMFERENCE * (1 - clamped / 100);

  return (
    <section
      data-testid="score-card"
      aria-label="진단 점수"
      className="flex flex-col items-center gap-5 rounded-md border border-neutral-800 bg-neutral-900/60 p-6 sm:flex-row sm:items-center sm:gap-8"
    >
      <svg
        viewBox="0 0 160 160"
        className="h-40 w-40 shrink-0"
        role="img"
        aria-label={`점수 ${clamped}점, 등급 ${grade ?? '미정'}`}
      >
        <circle
          cx="80"
          cy="80"
          r={RADIUS}
          fill="none"
          stroke="#262626"
          strokeWidth="12"
        />
        <circle
          cx="80"
          cy="80"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 80 80)"
        />
        <text
          x="80"
          y="74"
          textAnchor="middle"
          fontSize="34"
          fontWeight="700"
          fill="#f5f5f5"
        >
          {score ?? '-'}
        </text>
        <text x="80" y="100" textAnchor="middle" fontSize="13" fill="#a3a3a3">
          100점 만점
        </text>
        <text
          x="80"
          y="128"
          textAnchor="middle"
          fontSize="20"
          fontWeight="700"
          fill={color}
        >
          {grade ?? '?'}등급
        </text>
      </svg>

      <div className="flex w-full flex-col gap-3">
        <h2 className="text-sm font-semibold text-neutral-300">3축 잔여 예산</h2>
        {(Object.keys(AXIS_CAPS) as AxisKey[]).map((axis) => {
          const cap = AXIS_CAPS[axis];
          const remaining = Math.max(0, Math.min(cap, scoreDetail?.[axis] ?? cap));
          const ratio = remaining / cap;
          return (
            <div key={axis} className="flex items-center gap-3">
              <span className="w-14 shrink-0 text-xs text-neutral-400">
                {AXIS_LABELS[axis]} {cap}
              </span>
              <div
                className="h-2.5 flex-1 overflow-hidden rounded-full bg-neutral-800"
                role="img"
                aria-label={`${AXIS_LABELS[axis]} 잔여 ${remaining}/${cap}`}
              >
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.round(ratio * 100)}%`, backgroundColor: color }}
                />
              </div>
              <span className="w-12 shrink-0 text-right text-xs tabular-nums text-neutral-400">
                {remaining}/{cap}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
