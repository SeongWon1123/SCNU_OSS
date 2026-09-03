// Design tokens — single source for grade/severity colors (SPEC §8 등급 색).
// Imported by tailwind.config.ts (class utilities) and by SVG components (stroke/fill props).
export type Grade = 'A' | 'B' | 'C' | 'D' | 'F';

export const GRADE_COLORS: Record<Grade, string> = {
  A: '#34d399', // green
  B: '#60a5fa', // blue
  C: '#facc15', // yellow
  D: '#fb923c', // orange
  F: '#f87171', // red
};

export const NEUTRAL_GRADE_COLOR = '#a3a3a3'; // score/grade not ready yet

export function gradeColor(grade: string | null | undefined): string {
  if (grade && grade in GRADE_COLORS) {
    return GRADE_COLORS[grade as Grade];
  }
  return NEUTRAL_GRADE_COLOR;
}

export const SEVERITY_COLORS: Record<string, string> = {
  critical: '#f87171',
  high: '#fb923c',
  medium: '#facc15',
  low: '#60a5fa',
  info: '#94a3b8',
};

export function severityColor(severity: string): string {
  return SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.info;
}

// Axis caps — SPEC §6: 보안 40 · 규제 40 · 라이선스 20.
export const AXIS_CAPS = {
  security: 40,
  regulation: 40,
  license: 20,
} as const;

export type AxisKey = keyof typeof AXIS_CAPS;

export const AXIS_LABELS: Record<AxisKey, string> = {
  security: '보안',
  regulation: '규제',
  license: '라이선스',
};
