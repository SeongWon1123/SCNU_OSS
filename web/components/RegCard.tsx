// RegCard — 규제 탭의 R별 카드: 의무·기관·조문 링크·confidence 뱃지·파일:라인·왜·어떻게.
// 룰 표시 정보는 rules/catalog.yaml의 name/agency/law/source_url만 가져온 정적 지도
// (금액·형량 수치 없음 — AGENTS.md 절대규칙 2).
'use client';

import { useState } from 'react';
import { severityColor } from '@/lib/tokens';
import type { Finding } from '@/lib/types';

interface RegInfo {
  name: string;
  agency: string;
  law: string;
  sourceUrl: string;
}

const REG_INFO: Record<string, RegInfo> = {
  R1: {
    name: '위치기반서비스사업 신고',
    agency: '방송미디어통신위원회',
    law: '위치정보의 보호 및 이용 등에 관한 법률 제9조',
    sourceUrl: 'https://www.law.go.kr/법령/위치정보의보호및이용등에관한법률',
  },
  R2: {
    name: '개인정보처리방침 공개·적법 처리 근거',
    agency: '개인정보보호위원회',
    law: '개인정보보호법 제30조, 제15조',
    sourceUrl: 'https://www.law.go.kr/법령/개인정보보호법',
  },
  R3: {
    name: '통신판매업 신고',
    agency: '시·군·구청',
    law: '전자상거래 등에서의 소비자보호에 관한 법률 제12조',
    sourceUrl: 'https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률',
  },
  R5: {
    name: '광고성 정보 전송 사전 동의·수신거부 안내',
    agency: '방송미디어통신위원회 / KISA',
    law: '정보통신망 이용촉진 및 정보보호 등에 관한 법률 제50조',
    sourceUrl: 'https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률',
  },
  R6: {
    name: '생성형 AI 산출물 표시·이용자 고지',
    agency: '과학기술정보통신부',
    law: '인공지능 발전과 신뢰 기반 조성 등에 관한 기본법 제31조',
    sourceUrl: 'https://www.law.go.kr/법령/인공지능발전과신뢰기반조성등에관한기본법',
  },
  R7: {
    name: '주민등록번호 등 고유식별정보 처리 제한',
    agency: '개인정보보호위원회',
    law: '개인정보보호법 제24조',
    sourceUrl: 'https://www.law.go.kr/법령/개인정보보호법',
  },
};

const MAX_LOCATIONS = 5;

export default function RegCard({
  regRule,
  findings,
  revealed,
}: {
  regRule: string;
  findings: Finding[];
  revealed: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const info = REG_INFO[regRule];
  const totalWeight = findings.reduce((sum, f) => sum + f.weight, 0);
  const locations = expanded ? findings : findings.slice(0, MAX_LOCATIONS);

  return (
    <article
      data-testid={`reg-card-${regRule}`}
      className="flex flex-col gap-3 rounded-md border border-neutral-800 bg-neutral-900/60 p-4"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-emerald-400/15 px-2 py-0.5 text-xs font-bold text-emerald-400">
          {regRule}
        </span>
        <h3 className="text-sm font-semibold text-neutral-100">
          {info?.name ?? '확인이 필요한 규제 신호'}
        </h3>
        <span className="ml-auto text-xs tabular-nums text-neutral-500">
          감점 {totalWeight} · 신호 {findings.length}건
        </span>
      </header>

      {info && (
        <dl className="flex flex-col gap-1 text-xs leading-relaxed text-neutral-400">
          <div className="flex gap-1.5">
            <dt className="shrink-0 text-neutral-500">기관</dt>
            <dd>{info.agency}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="shrink-0 text-neutral-500">의무</dt>
            <dd>
              {info.law} —{' '}
              <a
                href={info.sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="underline decoration-neutral-600 underline-offset-2 hover:text-emerald-400"
              >
                법제처 원문 보기
              </a>
            </dd>
          </div>
        </dl>
      )}

      <ul className="flex flex-col gap-3">
        {locations.map((f) => (
          <li key={f.id} className="flex flex-col gap-2 rounded-md bg-neutral-950/60 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-neutral-950"
                style={{ backgroundColor: severityColor(f.severity) }}
              >
                {f.severity}
              </span>
              {f.confidence && (
                <span
                  data-testid="confidence-badge"
                  className="rounded border border-neutral-700 px-1.5 py-0.5 text-[11px] text-neutral-300"
                >
                  확실도 {f.confidence}
                </span>
              )}
              {f.file_path && (
                <code className="text-xs text-neutral-400">
                  {f.file_path}
                  {f.line_start != null && `:${f.line_start}`}
                  {f.line_end != null && f.line_end !== f.line_start && `-${f.line_end}`}
                </code>
              )}
            </div>
            <p className="text-sm font-medium text-neutral-100">{f.title_ko}</p>
            {f.snippet && (
              <pre className="overflow-x-auto rounded bg-neutral-900 p-2 text-xs leading-relaxed text-neutral-400">
                <code>{f.snippet}</code>
              </pre>
            )}
            {revealed && f.explain_ko && (
              <p className="text-sm leading-relaxed text-neutral-300">
                <span className="font-semibold text-emerald-400">왜 </span>
                {f.explain_ko}
              </p>
            )}
            {revealed && f.fix_ko && (
              <p className="text-sm leading-relaxed text-neutral-300">
                <span className="font-semibold text-emerald-400">어떻게 </span>
                {f.fix_ko}
              </p>
            )}
          </li>
        ))}
      </ul>

      {findings.length > MAX_LOCATIONS && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="self-start text-xs text-emerald-400 hover:underline"
        >
          {expanded ? '접기' : `더보기 (나머지 ${findings.length - MAX_LOCATIONS}건)`}
        </button>
      )}
    </article>
  );
}
