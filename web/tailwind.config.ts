import type { Config } from 'tailwindcss';

// SPEC §8: Tailwind, 다크 기본. Palette stays on the Tailwind default scale until
// a dedicated token layer is introduced in a later phase.
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
