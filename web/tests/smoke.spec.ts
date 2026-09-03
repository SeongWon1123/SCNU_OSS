import { expect, test } from '@playwright/test';

test('landing renders the hero', async ({ page }) => {
  await page.goto('http://localhost:3000/');
  await expect(
    page.getByRole('heading', {
      name: '바이브코딩한 내 서비스, 배포해도 되나요?',
    }),
  ).toBeVisible();
});
