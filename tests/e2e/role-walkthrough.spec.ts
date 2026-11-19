import { expect, test, type Dialog, type Page } from "@playwright/test";

const roles = [
  { account: "author", password: "AuthorDemo2026!", label: "作者", heading: "我的投稿", tasks: "作者待办", mail: false },
  { account: "reviewer", password: "ReviewerDemo2026!", label: "审稿人", heading: "我的审稿邀请", tasks: "审稿待办", mail: false },
  { account: "editor", password: "EditorDemo2026!", label: "编辑", heading: "待我处理的稿件", tasks: "编辑待办", mail: true },
  { account: "chief", password: "ChiefDemo2026!", label: "主编", heading: "期刊稿件", tasks: "主编待办", mail: true },
  { account: "production", password: "ProductionDemo2026!", label: "制作编辑", heading: "我的制作任务", tasks: "制作待办", mail: false },
] as const;

async function login(page: Page, role: typeof roles[number]) {
  const health = await page.request.get("/api/health");
  expect(health.ok()).toBe(true);
  expect(await health.json()).toMatchObject({ email_send_enabled: false, editorial_model: { provider: "mock" } });
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role.account}@publishing.test`);
  await page.getByLabel("密码", { exact: true }).fill(role.password);
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await page.getByRole("button", { name: "出版工作台", exact: true }).click();
  await expect(page.getByRole("heading", { name: role.heading, exact: true })).toBeVisible();
}

for (const role of roles) {
  test(`${role.label}从登录进入本人工作区并打开适用设置`, async ({ page }) => {
    await login(page, role);
    const sidebar = page.getByRole("complementary", { name: "我的工作" });
    await expect(sidebar.getByRole("button", { name: new RegExp(`^${role.tasks}`) })).toBeVisible();
    await expect(sidebar.getByRole("button", { name: "新建投稿", exact: true })).toHaveCount(role.account === "author" ? 1 : 0);
    await expect(sidebar.getByRole("link", { name: "内部审阅资料", exact: true })).toHaveCount(role.mail ? 1 : 0);
    const composer = page.getByRole("textbox", { name: "向出版助手发送消息" });
    await composer.fill("仅供角色走查的对话草稿");
    const settingsButton = sidebar.getByRole("button", { name: "设置", exact: true });
    await settingsButton.click();
    const settings = page.getByRole("dialog", { name: "设置" });
    await expect(settings.getByRole("heading", { name: "模型 API", exact: true })).toBeVisible();
    await expect(settings.getByRole("tab", { name: "邮箱", exact: true })).toHaveCount(role.mail ? 1 : 0);
    await page.keyboard.press("Escape");
    await expect(composer).toHaveValue("仅供角色走查的对话草稿");
    await expect(settingsButton).toBeFocused();
  });
}

test("窄屏工作列表隔离键盘焦点，Escape 恢复入口", async ({ page }) => {
  await login(page, roles[1]);
  await page.setViewportSize({ width: 390, height: 844 });
  const opener = page.getByRole("button", { name: "打开工作列表" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const closer = page.getByRole("button", { name: "关闭工作列表", exact: true });
  await expect(closer).toBeFocused();
  const drawer = page.getByRole("dialog", { name: "我的工作" });
  const last = drawer.getByRole("link", { name: "返回主工作台" });
  const search = drawer.getByRole("searchbox", { name: "全局搜索" });
  await closer.press("Shift+Tab");
  await expect(last).toBeFocused();
  await last.press("Tab");
  await expect(closer).toBeFocused();
  await closer.press("Tab");
  await expect(search).toBeFocused();
  await expect(page.locator('section[aria-label="出版助手"]')).toHaveAttribute("inert", "");
  await expect(page.locator('main[aria-label="稿件材料"]')).toHaveAttribute("inert", "");
  await page.screenshot({ path: test.info().outputPath("工作列表-390px.png") });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(opener).toBeFocused();
  await expect(opener).toHaveAttribute("aria-expanded", "false");
  await opener.click();
  await drawer.getByRole("button", { name: "设置", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "设置" });
  await expect(settings.getByRole("heading", { name: "模型 API", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await opener.click();
  await page.setViewportSize({ width: 1240, height: 840 });
  await expect(drawer).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(opener).toHaveAttribute("aria-expanded", "false");
});

test("作者取消离开时，新建投稿不产生空稿", async ({ page }) => {
  await login(page, roles[0]);
  const newDraft = page.getByRole("button", { name: "新建投稿", exact: true });
  await newDraft.click();
  const title = page.getByLabel("标题", { exact: true });
  await title.fill("未保存的合成题名");
  await page.getByRole("link", { name: "跳到对话", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#publishing-chat$/);
  const current = page.url();
  const selected = page.getByRole("complementary", { name: "我的工作" }).locator(`a[href="${new URL(current).pathname + new URL(current).search}"]`);
  const unexpected: string[] = [];
  const dismiss = (dialog: Dialog) => {
    unexpected.push(dialog.message());
    void dialog.dismiss();
  };
  page.on("dialog", dismiss);
  await selected.click();
  page.off("dialog", dismiss);
  expect(unexpected).toEqual([]);
  const created: string[] = [];
  page.on("request", request => {
    if (request.method() === "POST" && request.url().endsWith("/api/publishing/drafts")) created.push(request.url());
  });
  const dialog = page.waitForEvent("dialog").then(dialog => dialog.dismiss());
  await newDraft.click();
  await dialog;
  await expect(page).toHaveURL(current);
  await expect(title).toHaveValue("未保存的合成题名");
  expect(created).toHaveLength(0);
});

test("工作区读取延迟时显示载入状态，收到真实结果后更新", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/publishing/workspace?role_view=true", async route => {
    await gate;
    await route.continue();
  });
  try {
    await login(page, roles[1]);
    const sidebar = page.getByRole("complementary", { name: "我的工作" });
    const materials = page.getByRole("main", { name: "稿件材料" });
    await expect(sidebar.getByRole("status").getByText("正在载入待办…")).toBeVisible();
    await expect(materials.getByRole("status").getByText("正在载入稿件…")).toBeVisible();
    await expect(materials.getByText("目前没有发给你的审稿邀请。", { exact: true })).toHaveCount(0);
    const loaded = page.waitForResponse(response => response.url().endsWith("/api/publishing/workspace?role_view=true"));
    release();
    expect((await loaded).ok()).toBe(true);
    await expect(materials.getByText("正在载入稿件…", { exact: true })).toHaveCount(0);
  } finally {
    release();
  }
});

test("新建请求等待期间的新编辑仍受离开保护", async ({ page }) => {
  await login(page, roles[0]);
  const newDraft = page.getByRole("button", { name: "新建投稿", exact: true });
  await newDraft.click();
  const title = page.getByLabel("标题", { exact: true });
  await title.fill("发起新建前的合成题名");
  const current = page.url();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let requestStarted!: () => void;
  const started = new Promise<void>(resolve => { requestStarted = resolve; });
  await page.route("**/api/publishing/drafts", async route => {
    requestStarted();
    await gate;
    await route.continue();
  });
  try {
    const initial = page.waitForEvent("dialog").then(dialog => dialog.accept());
    await newDraft.click();
    await initial;
    await started;
    await page.getByRole("button", { name: "添加作者", exact: true }).click();
    await expect(page.getByLabel("姓名", { exact: true })).toHaveCount(2);
    const leaving = page.waitForEvent("dialog").then(dialog => dialog.dismiss());
    release();
    await leaving;
    await expect(page).toHaveURL(current);
    await expect(title).toHaveValue("发起新建前的合成题名");
    await expect(page.getByLabel("姓名", { exact: true })).toHaveCount(2);
    await expect(newDraft).toBeEnabled();
  } finally {
    release();
  }
});

test.describe("移动工作列表中的稿件链接", () => {
  test.use({ timezoneId: "UTC" });

  test("从真实待办日历打开稿件后收起抽屉", async ({ page }) => {
    await login(page, roles[0]);
    await page.getByRole("button", { name: "新建投稿", exact: true }).click();
    await expect(page.getByLabel("标题", { exact: true })).toBeVisible();
    const manuscriptId = new URL(page.url()).searchParams.get("manuscript");
    const workspace = await (await page.request.get("/api/publishing/workspace?role_view=true")).json();
    const task = workspace.tasks.find((item: { manuscript_id: string }) => item.manuscript_id === manuscriptId);
    const deadline = task.due_at.slice(0, 10);
    await page.goto("/publishing");
    await page.setViewportSize({ width: 390, height: 844 });
    const opener = page.getByRole("button", { name: "打开工作列表", exact: true });
    await opener.click();
    const drawer = page.getByRole("dialog", { name: "我的工作" });
    const calendar = drawer.getByRole("region", { name: "个人日历" });
    await calendar.getByRole("button", { name: "日历", exact: true }).click();
    await calendar.getByLabel("截止日期", { exact: true }).fill(deadline);
    const link = calendar.getByRole("list", { name: "截止任务" }).getByRole("link").first();
    const target = await link.getAttribute("href");
    expect(target).toMatch(/^\/publishing\?manuscript=/);
    await link.click();
    await expect(page).toHaveURL(url => url.pathname + url.search === target);
    await expect(drawer).toHaveCount(0);
    await expect(opener).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByLabel("标题", { exact: true })).toBeVisible();
  });
});
