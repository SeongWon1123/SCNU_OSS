import { expect, type Page, test } from '@playwright/test';

// E2E — caddy(:80) 경유 전체 플로우. GITHUB_TOKEN 불필요: 전부 DB fixture 스캔 기반.
// fixture 스캔(INSERT 값은 증거 task-17 txt에 기록):
//   a = 11111111-1111-1111-1111-111111111111 (done, score 60/C, findings 3)
//   b = 22222222-2222-2222-2222-222222222222 (queued, queue_position 2)
//   c = 33333333-3333-3333-3333-333333333333 (done, score 100/A, findings 0)

const SCAN_A = '11111111-1111-1111-1111-111111111111';
const SCAN_B = '22222222-2222-2222-2222-222222222222';
const SCAN_C = '33333333-3333-3333-3333-333333333333';
const TOKEN_A = 'tok-a-repodoc-e2e';
const TOKEN_B = 'tok-b-repodoc-e2e';
const TOKEN_C = 'tok-c-repodoc-e2e';
const BAD_ID = '00000000-0000-0000-0000-000000000000';

const EVIDENCE_DIR = process.env.EVIDENCE_DIR || '/evidence';

// caddy :80 블록에는 try_files가 없어 /scan 직접 진입은 404다 (실측).
// 정적 export의 scan.html은 caddy file_server로 서빙되며 그대로 하이드레이션된다 —
// fixture 스캔 진입은 /scan.html?id=&t= 직접 이동으로 고정한다 (실측 probe).
async function openScan(page: Page, id: string, token = ''): Promise<void> {
  const query = token ? `&t=${encodeURIComponent(token)}` : '';
  await page.goto(`/scan.html?id=${id}${query}`);
}

test('랜딩 렌더 + 입력 → /scan 진입', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '바이브코딩한 내 서비스, 배포해도 되나요?' })).toBeVisible();
  await expect(page.getByTestId('consent')).toBeVisible();
  // fixture a(c consent=true·done)와 c(consent=false·done) 중 a만 recent에 노출
  await expect(page.getByTestId('recent-list')).toContainText('octocat/fixture-a');
  // /api/stats는 todo 19(routers/stats.py)에서 제공 — 현재 404라 stats-line은 의도적으로 숨김.
  await page.screenshot({ path: `${EVIDENCE_DIR}/task-17-repodoc-kickoff-landing.png` });

  await page.getByTestId('repo-url').fill('https://github.com/psf/requests');
  await page.getByTestId('submit').click();
  await page.waitForURL(/\/scan\?id=/);
  await expect(page.getByTestId('progress-steps').or(page.getByTestId('error-state'))).toBeVisible({
    timeout: 15000,
  });
});

test('로딩 화면 — fixture b(queued, 대기 순번 2)', async ({ page }) => {
  await openScan(page, SCAN_B, TOKEN_B);
  await expect(page.getByTestId('progress-steps')).toBeVisible();
  await expect(page.getByTestId('queue-position')).toHaveText('대기 순번 2번');
  await expect(page.getByRole('progressbar')).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/task-17-repodoc-kickoff-loading.png` });
});

test('결과 화면 — fixture a(60/C): 탭·토글 OFF 시 해설 숨김 + 점수 불변', async ({ page }) => {
  await openScan(page, SCAN_A, TOKEN_A);
  const scoreCard = page.getByTestId('score-card');
  await expect(scoreCard).toContainText('60');
  await expect(scoreCard).toContainText('C등급');
  await expect(page.getByTestId('llm-panel')).toBeVisible();
  await expect(page.getByTestId('llm-status')).toContainText('해설 생략'); // 키 없음 — skipped가 정상

  // 규제 탭 (기본)
  await expect(page.getByTestId('reg-tab')).toHaveAttribute('aria-selected', 'true');
  const regCard = page.getByTestId('reg-card-R1');
  await expect(regCard).toBeVisible();
  await expect(regCard).toContainText('방송미디어통신위원회');
  await expect(regCard).toContainText('법제처 원문 보기');
  await expect(page.getByTestId('confidence-badge').first()).toBeVisible();
  const explain = regCard.getByText('브라우저 위치 API를 서버와 연동하면');
  await expect(explain).toBeVisible();

  // 토글 OFF — explain_ko/fix_ko 숨김, 점수·건수 불변
  await page.getByTestId('llm-toggle').click();
  await expect(page.getByTestId('llm-toggle')).toContainText('해설 켜기');
  await expect(explain).toBeHidden();
  await expect(regCard.getByText('어떻게')).toHaveCount(0);
  await expect(scoreCard).toContainText('60');
  await expect(page.getByTestId('llm-panel')).toContainText('호출');
  await expect(page.getByTestId('llm-panel')).toContainText('0회');

  // 보안 탭 — 마스킹 스니펫
  await page.getByTestId('security-tab').click();
  await expect(page.getByTestId('masked-snippet')).toContainText('AK****');

  // 라이선스 탭
  await page.getByTestId('license-tab').click();
  await expect(page.getByTestId('license-list')).toBeVisible();

  await page.screenshot({ path: `${EVIDENCE_DIR}/task-17-repodoc-kickoff-result.png` });
});

test('결과 상단이 1024×768에서 한 화면 — 점수 카드 + 첫 R 카드', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await openScan(page, SCAN_A, TOKEN_A);
  await expect(page.getByTestId('score-card')).toBeVisible();
  const regCard = page.getByTestId('reg-card-R1');
  await expect(regCard).toBeVisible();
  const box = await regCard.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeLessThan(768); // 첫 R 카드가 첫 화면 안에서 시작
});

test('빈 상태 — fixture c(100/A) + 확인 질문 6가지', async ({ page }) => {
  await openScan(page, SCAN_C, TOKEN_C);
  const empty = page.getByTestId('empty-state');
  await expect(empty).toBeVisible();
  await expect(empty).toContainText('100');
  await expect(empty).toContainText('A등급');
  await expect(empty).toContainText('탐지 없음 ≠ 의무 없음 — 직접 확인할 6가지');
  expect(await empty.getByRole('checkbox').count()).toBe(6);
  await page.screenshot({ path: `${EVIDENCE_DIR}/task-17-repodoc-kickoff-empty.png` });
});

test('잘못된 id → error-state', async ({ page }) => {
  await openScan(page, BAD_ID);
  await expect(page.getByTestId('error-state')).toBeVisible();
  await expect(page.getByTestId('error-reason')).toContainText('스캔을 찾을 수 없습니다'); // 서버 detail 그대로 노출
});

test('375×667 결과 화면', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await openScan(page, SCAN_A, TOKEN_A);
  await expect(page.getByTestId('score-card')).toBeVisible();
  await expect(page.getByTestId('reg-tab')).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/task-17-repodoc-kickoff-375.png` });
});
