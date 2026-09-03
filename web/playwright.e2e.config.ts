import { defineConfig } from '@playwright/test';

// E2E — caddy(localhost:80)가 서빙하는 스택 대상. webServer 없음 (todo-5 smoke 전용 유지).
// 실행: docker run --rm --network host -v "$(pwd)/web":/w node:20 npx playwright test -c playwright.e2e.config.ts
export default defineConfig({
  testDir: './tests',
  testMatch: 'e2e.spec.ts',
  outputDir: 'test-results/e2e',
  use: {
    baseURL: 'http://localhost',
    viewport: { width: 1280, height: 720 },
  },
});
