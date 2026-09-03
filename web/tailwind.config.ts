import type { Config } from 'tailwindcss';
import { GRADE_COLORS, SEVERITY_COLORS } from './lib/tokens';

// SPEC §8: Tailwind, 다크 기본. Grade/severity colors are semantic tokens sourced
// from lib/tokens.ts (same constants the SVG components use) — no hardcoded hex in JSX.
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        grade: {
          a: GRADE_COLORS.A,
          b: GRADE_COLORS.B,
          c: GRADE_COLORS.C,
          d: GRADE_COLORS.D,
          f: GRADE_COLORS.F,
        },
        severity: {
          critical: SEVERITY_COLORS.critical,
          high: SEVERITY_COLORS.high,
          medium: SEVERITY_COLORS.medium,
          low: SEVERITY_COLORS.low,
          info: SEVERITY_COLORS.info,
        },
      },
    },
  },
  plugins: [],
};

export default config;
