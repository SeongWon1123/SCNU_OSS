import { defineConfig } from '@playwright/test';

// Serves the static export (web/out) for smoke tests. Run from web/: npx playwright test smoke
export default defineConfig({
  testDir: './tests',
  use: {
    viewport: { width: 375, height: 667 }, // SPEC §8: 375px 검수
  },
  webServer: {
    command: 'npx serve out -l 3000',
    port: 3000,
    reuseExistingServer: true,
    cwd: __dirname,
  },
});
