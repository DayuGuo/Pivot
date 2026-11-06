import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function login(page: Page, role = "editor") {
  const health = await (await page.request.get("/api/health")).json();
  expect(health.editorial_model.provider).toBe("mock");
  const passwords: Record<string, string> = { editor: "EditorDemo2026!", author: "AuthorDemo2026!", reviewer: "ReviewerDemo2026!" };
  const response = await page.request.post("/api/auth/login", { data: { email: `${role}@publishing.test`, password: passwords[role] } });
  expect(response.status()).toBe(200);
  return await (await page.request.get("/api/publishing/session")).json();
}

async function open(page: Page) {
  const button = page.getByRole("button", { name: "设置", exact: true });
  await button.click();
  const panel = page.getByRole("dialog", { name: "设置", exact: true });
  await expect(panel.getByRole("heading", { name: "模型 API", exact: true })).toBeVisible();
  return panel;
}

test("设置：真实配置只读、键盘操作与对话草稿保留", async ({ page }) => {
  await login(page); await page.goto("/");
  const input = page.getByRole("textbox", { name: "对话指令", exact: true });
  await input.fill("打开设置时保留这份未发送的草稿。");
  const errors: string[] = [], posts: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.method() === "POST") posts.push(request.url()); });
  const panel = await open(page);
  await expect(panel.getByText("Mock（模拟）", { exact: true })).toBeVisible();
  await panel.getByText("配置 DeepSeek API", { exact: true }).click();
  await expect(panel.getByText("DEEPSEEK_API_KEY", { exact: true })).toBeVisible();
  await expect(panel.locator('input[type="password"]')).toHaveCount(0);
  const refreshed = page.waitForResponse(response => response.url().endsWith("/api/publishing/session"));
  await panel.getByRole("button", { name: "刷新模型配置", exact: true }).click(); await refreshed;
  await expect(panel.getByText("Mock（模拟）", { exact: true })).toBeVisible();
  await page.screenshot({ path: `artifacts/settings-${test.info().project.name}-desktop.png`, fullPage: true });
  await panel.getByRole("tab", { name: "模型 API", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(panel.getByRole("tab", { name: "账号", exact: true })).toBeFocused();
  await expect(panel.getByRole("heading", { name: "账号", exact: true })).toBeVisible();
  await page.keyboard.press("Escape"); await expect(panel).toHaveCount(0);
  await expect(input).toHaveValue("打开设置时保留这份未发送的草稿。");
  await expect(page.getByRole("button", { name: "设置", exact: true })).toBeFocused();
  expect(posts).toEqual([]); expect(errors).toEqual([]);
});

test("设置：资料、正式出版与演示工作台共用入口，不切稿或清草稿", async ({ page }) => {
  const session = await login(page);
  const headers = { "X-CSRF-Token": session.csrf_token };
  const response = await page.request.post("/api/dossiers", { headers, data: { request_id: randomUUID(), title: "完全合成的设置回归稿件", source_kind: "synthetic", source_note: "全部为自动测试原创合成资料。", authorized_material: true } });
  expect(response.status()).toBe(200); const { dossier_id: id } = await response.json();
  const before = await (await page.request.get(`/api/dossiers/${id}`)).json();
  const save = await page.request.post(`/api/dossiers/${id}/versions`, { headers, data: { request_id: randomUUID(), expected_revision: before.revision, data: before.data, file: { filename: "settings-synthetic.txt", content_base64: Buffer.from("完全合成的正文，仅验证设置不会改变稿件与对话。 ").toString("base64") } } });
  expect(save.status()).toBe(200);
  await page.goto(`/library?dossier=${id}`);
  const question = page.getByRole("textbox", { name: "询问当前资料", exact: true });
  await expect(question).toBeEnabled(); await question.fill("这份稿件的草稿不要丢失。");
  const url = page.url(); const panel = await open(page);
  await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  await expect(page).toHaveURL(url); await expect(question).toHaveValue("这份稿件的草稿不要丢失。");
  for (const path of ["/publishing", "/workbench"]) {
    await page.goto(path); const settings = await open(page);
    await settings.getByRole("button", { name: "关闭设置", exact: true }).click();
    expect(new URL(page.url()).pathname).toBe(path);
  }
});

test("UI fixture：长资料列表独立滚动，身份和设置入口始终可点击", async ({ page }) => {
  await login(page);
  // Synthetic list projection isolates layout from the number of existing DB rows.
  await page.route(/\/api\/dossiers(?:\?|$)/, route => route.fulfill({ json: {
    items: Array.from({ length: 30 }, (_, index) => ({
      id: randomUUID(), version_id: randomUUID(), revision: 1, version_no: 1,
      title: `合成的长题名资料 ${index + 1}：多机构研究方法与审阅证据 ${randomUUID()}`,
      verified: false, updated_at: "2026-11-06T00:00:00Z",
    })), next_cursor: null,
  } }));
  await page.goto("/library");
  const sidebar = page.getByRole("complementary", { name: "我的资料", exact: true });
  const list = sidebar.getByRole("navigation");
  await expect(list.getByRole("link")).toHaveCount(30);
  await expect(list.getByRole("link").first()).toContainText("合成的长题名资料 1：");
  const settings = sidebar.getByRole("button", { name: "设置", exact: true });
  const initial = await settings.boundingBox();
  expect(initial).not.toBeNull();
  expect(initial!.y).toBeGreaterThanOrEqual(0);
  expect(initial!.y + initial!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  await list.getByRole("link").last().scrollIntoViewIfNeeded();
  expect(await list.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  const panel = await open(page);
  await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  await expect(sidebar.locator('summary[aria-label="切换身份"]')).toBeVisible();
  await sidebar.locator('summary[aria-label="切换身份"]').click();
  await expect(sidebar.getByRole("list", { name: "当前账号的可用身份" })).toBeVisible();
  await page.screenshot({ path: `artifacts/identity/${test.info().project.name}-long-sidebar.png`, fullPage: true });
  await page.keyboard.press("Escape");
  const final = await settings.boundingBox();
  expect(Math.abs(final!.y - initial!.y)).toBeLessThanOrEqual(1);
});

test("设置：邮箱草稿跨分类保留，配置读取失败不丢草稿，关闭须确认", async ({ page }) => {
  await login(page); await page.goto("/"); const panel = await open(page);
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeEnabled();
  const address = `unsaved-${randomUUID().slice(0, 8)}@publishing.test`;
  await panel.getByLabel("邮箱地址", { exact: true }).fill(address);
  await panel.getByRole("button", { name: "使用本地 Mailpit", exact: true }).click();
  await panel.getByRole("tab", { name: "模型 API", exact: true }).click();
  await page.route("**/api/publishing/session", route => route.fulfill({ status: 503, json: { detail: "合成暂时不可用" } }), { times: 1 });
  await panel.getByRole("button", { name: "刷新模型配置", exact: true }).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  await panel.getByRole("button", { name: "重新读取设置", exact: true }).click();
  await expect(panel.getByRole("heading", { name: "模型 API", exact: true })).toBeVisible();
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(panel.getByLabel("邮箱地址", { exact: true })).toHaveValue(address);
  page.once("dialog", dialog => dialog.dismiss());
  await page.keyboard.press("Escape"); await expect(panel).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  await expect(panel).toHaveCount(0);
});

test("设置：作者与审稿人不可管理期刊邮箱", async ({ page }) => {
  for (const role of ["author", "reviewer"]) {
    await login(page, role); await page.goto("/"); const panel = await open(page);
    await expect(panel.getByRole("tab", { name: "邮箱", exact: true })).toHaveCount(0);
    await panel.getByRole("tab", { name: "账号", exact: true }).click();
    await expect(panel.getByText(`${role}@publishing.test`, { exact: true })).toBeVisible();
    expect((await page.request.get("/api/mail/accounts")).status()).toBe(403);
    await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  }
});

test("设置：关闭后的迟到配置不能覆盖再次打开的账号", async ({ page }) => {
  const session = await login(page); await page.goto("/");
  let release!: () => void, started!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const first = new Promise<void>(resolve => { started = resolve; });
  let calls = 0;
  await page.route("**/api/publishing/session", async route => {
    if (++calls === 1) { started(); await pending; await route.fulfill({ json: { ...session, user: { ...session.user, name: "不得恢复的过期账号" } } }).catch(() => {}); }
    else await route.fulfill({ json: session });
  });
  await page.getByRole("button", { name: "设置", exact: true }).click(); await first;
  await page.getByRole("button", { name: "关闭设置", exact: true }).click();
  const panel = await open(page); release();
  await panel.getByRole("tab", { name: "账号", exact: true }).click();
  await expect(panel.getByText(session.user.name, { exact: true })).toBeVisible();
  await expect(panel.getByText("不得恢复的过期账号", { exact: true })).toHaveCount(0);
});

test("设置：移动端原生面板布局、关闭和输入框恢复", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page); await page.goto("/publishing");
  const composer = page.getByRole("textbox", { name: "向出版助手发送消息", exact: true });
  await composer.fill("移动端未发送草稿");
  await page.getByRole("button", { name: "打开工作列表", exact: true }).click();
  const panel = await open(page);
  const box = await panel.boundingBox(); expect(box?.width).toBeLessThanOrEqual(390); expect(box?.height).toBeLessThanOrEqual(844);
  expect(await panel.getByRole("button", { name: "关闭设置", exact: true }).evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  await page.screenshot({ path: `artifacts/settings-${test.info().project.name}-mobile-model.png`, fullPage: true });
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(panel.getByLabel("邮箱地址", { exact: true })).toBeVisible();
  expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.screenshot({ path: `artifacts/settings-${test.info().project.name}-mobile-mail.png`, fullPage: true });
  await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  await expect(composer).toHaveValue("移动端未发送草稿");
  await expect(page.getByRole("button", { name: "打开工作列表", exact: true })).toBeFocused();
});

test("设置：Ctrl/Cmd+K 不得切换底层稿件阅读页面", async ({ page }) => {
  await login(page);
  const data = await (await page.request.get("/api/editorial-demo")).json();
  await page.goto(`/workbench?view=read&case=${data.cases[0].id}`);
  const breadcrumb = page.locator("header strong").filter({ hasText: /^稿件阅读$/ });
  await expect(breadcrumb).toBeVisible();
  const url = page.url(), panel = await open(page);
  await panel.getByRole("tab", { name: "模型 API", exact: true }).focus();
  await page.keyboard.press("Control+k");
  await page.keyboard.press("Meta+k");
  await panel.getByRole("button", { name: "关闭设置", exact: true }).click();
  await expect(breadcrumb).toBeVisible(); await expect(page).toHaveURL(url);
});

test("设置：深色面板沿用当前主题，邮件状态保持可读", async ({ page }) => {
  await login(page); await page.goto("/publishing");
  await page.getByLabel("外观", { exact: true }).selectOption("dark");
  const panel = await open(page);
  await expect(panel).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: `artifacts/settings-${test.info().project.name}-dark-model.png`, fullPage: true });
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeEnabled();
  // Temporary DOM-only probes measure the shipped semantic classes, without
  // claiming a remote mailbox was authenticated or modifying any account.
  const ratios = await panel.evaluate(element => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
    const light = (channels: number[]) => channels.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
    const base = light(rgb(getComputedStyle(element).backgroundColor));
    const host = element.querySelector(".mail-settings")!;
    return ["status-verified", "status-credentials_required"].map(className => {
      const probe = document.createElement("span"); probe.className = `mail-status ${className}`; probe.textContent = "合成颜色检查"; host.append(probe);
      const foreground = light(rgb(getComputedStyle(probe).color)); probe.remove();
      return (Math.max(base, foreground) + 0.05) / (Math.min(base, foreground) + 0.05);
    });
  });
  expect(ratios.every(ratio => ratio >= 4.5)).toBe(true);
  await page.screenshot({ path: `artifacts/settings-${test.info().project.name}-dark-mail.png`, fullPage: true });
});
