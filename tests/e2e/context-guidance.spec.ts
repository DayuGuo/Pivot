import { test, expect, type Page } from '@playwright/test';

async function context(page: Page) {
  const login = await page.request.post('/api/auth/login', { data: { email: 'editor@publishing.test', password: 'EditorDemo2026!' } });
  expect(login.status()).toBe(200);
  const auth = await login.json();
  const items = [];
  for (let i = 0; i < 2; i++) {
    const response = await page.request.post('/api/dossiers', {
      headers: { 'X-CSRF-Token': auth.csrf_token },
      data: { request_id: crypto.randomUUID(), title: `合成建议资料${i}-${Date.now()}`, source_kind: 'synthetic', source_note: '纯合成界面验收，不含保密信息。', authorized_material: true },
    });
    expect(response.status()).toBe(200);
    const id = (await response.json()).dossier_id;
    items.push(await (await page.request.get(`/api/dossiers/${id}`)).json());
  }
  return items;
}

test('真实缺项建议：保留输入、仅填草稿、刷新持久数据、窄屏可操作', async ({ page }) => {
  const [item] = await context(page);
  let posts = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/chat')) posts++; });
  await page.goto(`/library?dossier=${item.id}`);
  const hints = page.getByRole('complementary', { name: '下一步建议', exact: true });
  await expect(hints).toContainText('尚未录入可审阅全文');
  const composer = page.getByLabel('询问当前资料', { exact: true });
  await composer.fill('保留我的问题');
  await hints.getByRole('button', { name: '整理待补资料', exact: true }).click();
  await expect(composer).toHaveValue(/^保留我的问题\n\n请根据当前已保存资料/);
  expect(posts).toBe(0);
  await expect(composer).toBeFocused();
  const saved = await (await page.request.get(`/api/dossiers/${item.id}`)).json();
  expect(saved).toEqual(item);
  await page.screenshot({ path: test.info().outputPath('guidance-desktop.png') });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(hints.getByRole('button', { name: '整理待补资料', exact: true })).toBeVisible();
  await expect(composer).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('guidance-mobile.png') });
});

test('切换资料后迟到的建议不出现；错误版本的建议被丢弃', async ({ page }) => {
  const [first, second] = await context(page);
  let release!: () => void;
  let started = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/dossiers/${first.id}/guidance`, async route => {
    started = true;
    await gate;
    await route.fulfill({ json: { schema: 'next-steps.v1', object_id: first.id, version_id: first.version_id, revision: first.revision, role: 'editor', suggestions: [{ id: 'stale', label: '迟到旧建议', prompt: '迟到旧问题', reason: '旧稿依据' }] } });
  });
  await page.goto(`/library?dossier=${first.id}`);
  await expect.poll(() => started).toBe(true);
  await page.getByRole('link').filter({ hasText: second.data.title }).click();
  await expect(page.getByLabel('题名', { exact: true })).toHaveValue(second.data.title);
  await expect(page.getByRole('button', { name: '整理待补资料', exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('button', { name: '迟到旧建议', exact: true })).toHaveCount(0);
  await page.route(`**/api/dossiers/${second.id}/guidance`, route => route.fulfill({ json: { schema: 'next-steps.v1', object_id: second.id, version_id: first.version_id, revision: second.revision, role: 'editor', suggestions: [{ id: 'wrong', label: '错误版本建议', prompt: '错误版本问题', reason: '不匹配依据' }] } }));
  await page.getByRole('button', { name: '刷新下一步建议', exact: true }).click();
  await expect(page.getByRole('complementary', { name: '下一步建议', exact: true })).toContainText('稿件版本或身份已变化');
  await expect(page.getByRole('button', { name: '错误版本建议', exact: true })).toHaveCount(0);
});
