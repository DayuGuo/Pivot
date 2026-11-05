import { test, expect, type Page } from '@playwright/test';

async function login(page: Page, role = 'author') {
  const response = await page.request.post('/api/auth/login', {
    data: { email: `${role}@publishing.test`, password: role === 'author' ? 'AuthorDemo2026!' : 'EditorDemo2026!' },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

test('浏览器禁止本地存储时，出版对话仍可输入、发送和切换外观', async ({ page }) => {
  await login(page);
  await page.addInitScript(() => {
    for (const name of ['getItem', 'setItem', 'removeItem']) Object.defineProperty(Storage.prototype, name, { value: () => { throw new DOMException('Storage blocked', 'SecurityError'); } });
  });
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/publishing');
  const input = page.getByLabel('向出版助手发送消息', { exact: true });
  await input.fill('只读：我当前有哪些工作？');
  await page.getByLabel('外观', { exact: true }).selectOption('dark');
  await expect(page.locator('[data-theme="dark"]')).toBeVisible();
  const sent = page.waitForResponse(r => r.url().endsWith('/api/publishing/chat') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  expect((await sent).status()).toBe(200);
  await expect(input).toHaveValue('');
  expect(errors).toEqual([]);
});

test('缺少较新 UUID/取消请求 API 时，正式 Word 仍能提取与人工核对保存', async ({ page }) => {
  const auth = await login(page);
  const draft = await page.request.post('/api/publishing/drafts', { headers: { 'X-CSRF-Token': auth.csrf_token }, data: { request_id: crypto.randomUUID(), title: '合成浏览器功能降级回归' } });
  expect(draft.status()).toBe(200); const mid = (await draft.json()).manuscript_id;
  await page.addInitScript(() => {
    Object.defineProperty(crypto, 'randomUUID', { value: undefined });
    Object.defineProperty(AbortSignal, 'any', { value: undefined });
    Object.defineProperty(AbortSignal, 'timeout', { value: undefined });
  });
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(`/publishing?manuscript=${mid}`);
  await page.getByRole('link', { name: '导入 PDF / Word 并核对', exact: true }).click();
  await page.getByLabel('选择 PDF / Word', { exact: true }).setInputFiles('tests/documents/synthetic-unicode.docx');
  await page.getByLabel('来源与授权说明', { exact: true }).fill('纯合成兼容性验收，不含保密信息。');
  await page.getByRole('checkbox', { name: '我有权使用此资料', exact: false }).check();
  await page.getByRole('button', { name: '提取并打开核对页', exact: true }).click();
  await expect(page.getByLabel('待保存的提取全文', { exact: true })).toHaveValue(/𝛽 和 😀/);
  for (const name of ['我已核对原件及其来源授权', '我已对照原件核对提取全文，没有漏页或漏段', '我已核对所选范围符合文件用途，不混入评审附录或其他材料']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByRole('button', { name: '确认导入到当前草稿', exact: true }).click();
  await expect(page.getByLabel('已保存的提取全文', { exact: true })).toHaveValue(/𝛽 和 😀/);
  expect(errors).toEqual([]);
});

for (const [path, label] of [['/', '对话指令'], ['/demo', '对话消息'], ['/publishing', '向出版助手发送消息'], ['/workbench', '对话消息']] as const) {
  test(`中文输入法确认候选 Enter 不发送：${path}`, async ({ page }) => {
    await login(page, 'editor');
    let posts = 0; page.on('request', r => { if (r.method() === 'POST' && /\/(chat|commands)$/.test(new URL(r.url()).pathname)) posts++; });
    await page.goto(path);
    const input = page.getByRole('textbox', { name: label, exact: true });
    await input.fill('中文候选还未确认');
    // Safari may report isComposing=false on the candidate-confirmation keydown.
    await input.dispatchEvent('keydown', { key: 'Enter', keyCode: 229, which: 229, isComposing: false, bubbles: true, cancelable: true });
    await expect(input).toHaveValue('中文候选还未确认');
    await expect(input).toBeEnabled();
    expect(posts).toBe(0);
  });
}

test('375px短视口保持主体对话宽度，输入不触发小字号自动放大', async ({ page }) => {
  await login(page, 'editor'); await page.setViewportSize({ width: 375, height: 450 });
  for (const [path, name] of [['/publishing', '向出版助手发送消息'], ['/library', '询问当前资料'], ['/workbench?view=read&case=demo-001', '对话消息']] as const) {
    await page.goto(path); const input = page.getByRole('textbox', { name, exact: true });
    await expect(input).toBeVisible(); const box = (await input.boundingBox())!;
    expect(box.width).toBeGreaterThan(260); expect(box.y + box.height).toBeLessThanOrEqual(451);
    expect(await input.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
});
