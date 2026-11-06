import { test, expect, type Page } from "@playwright/test";

const command = "创建一篇测试稿件，并交给编辑初筛。";
async function login(page: Page, role: "editor" | "author" | "reviewer" = "editor") {
  const passwords = { editor: "EditorDemo2026!", author: "AuthorDemo2026!", reviewer: "ReviewerDemo2026!" };
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}@publishing.test`);
  await page.getByLabel("密码", { exact: true }).fill(passwords[role]);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
}

test("编辑登录、对话执行真实工具、数据库持久化与审计", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", error => consoleErrors.push(error.message));
  await login(page);
  await expect(page.getByText("Mock · 模拟模型", { exact: true })).toBeVisible();
  const before = await page.request.get("/api/workspace");
  expect(before.ok()).toBeTruthy();
  const previousCount = (await before.json()).manuscripts.length;
  await page.getByLabel("对话指令", { exact: true }).fill(command);
  const resultPromise = page.waitForResponse(response => response.url().endsWith("/api/conversations/commands") && response.request().method() === "POST");
  await page.getByRole("button", { name: "发送指令" }).click();
  const result = await resultPromise;
  expect(result.status()).toBe(200);
  const body = await result.json();
  const manuscript = body.manuscript;
  expect(manuscript.status).toBe("screening");
  expect(manuscript.task).toBeTruthy();
  await expect(page.getByTestId("manuscript-detail")).toContainText(manuscript.title);
  await expect(page.getByTestId("manuscript-detail").getByText("编辑初筛", { exact: true }).first()).toBeVisible();
  expect(body.provider).toBe("mock");
  await expect(page.getByText(/\[模拟结果 · Mock\]/).last()).toBeVisible();
  await page.screenshot({ path: "artifacts/editorial-workspace.png", fullPage: true });
  const after = await (await page.request.get("/api/workspace")).json();
  expect(after.manuscripts).toHaveLength(previousCount + 1);
  expect(after.email_send_enabled).toBe(false);
  expect(after.audit.some((event: { entity_id: string }) => event.entity_id === manuscript.id)).toBe(true);
  await page.reload();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: /稿件管理/ }).click();
  await page.getByRole("button").filter({ hasText: manuscript.id.slice(0, 8).toUpperCase() }).first().click();
  await expect(page.getByTestId("manuscript-detail")).toContainText(manuscript.title);
  const persisted = await (await page.request.get(`/api/manuscripts/${manuscript.id}`)).json();
  expect(persisted.status).toBe("screening");
  expect(persisted.task.id).toBe(manuscript.task.id);
  await page.getByRole("navigation").getByRole("button", { name: "审计记录" }).click();
  await expect(page.getByTestId("audit-list")).toContainText(manuscript.id.slice(0, 8).toUpperCase());
  await page.screenshot({ path: "artifacts/editorial-intake.png", fullPage: true });
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
  expect((await page.request.get("/api/workspace")).status()).toBe(401);
  expect(consoleErrors).toEqual([]);
});

test("作者与审稿人无法通过对话越权创建编辑任务", async ({ page }) => {
  for (const role of ["author", "reviewer"] as const) {
    await login(page, role);
    const before = await (await page.request.get("/api/workspace")).json();
    await page.getByLabel("对话指令", { exact: true }).fill(command);
    const rejected = page.waitForResponse(response => response.url().endsWith("/api/conversations/commands") && response.request().method() === "POST");
    await page.getByRole("button", { name: "发送指令" }).click();
    expect((await rejected).status()).toBe(403);
    await expect(page.getByRole("alert").filter({ hasText: "权限不足" })).toBeVisible();
    const after = await (await page.request.get("/api/workspace")).json();
    expect(after.manuscripts.length).toBe(before.manuscripts.length);
    expect(after.email_send_enabled).toBe(false);
    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page.getByRole("button", { name: "进入工作台" })).toBeVisible();
  }
});

test("错误密码不会建立会话", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({ path: "artifacts/hermes-login.png", fullPage: true });
  await page.getByLabel("密码", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "邮箱或密码" })).toBeVisible();
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("浏览器网关保留 CSRF 和跨站登录防护", async ({ page }) => {
  await login(page);
  const missingCsrf = await page.request.post("/api/conversations/commands", {
    data: { message: command, request_id: crypto.randomUUID() },
  });
  expect(missingCsrf.status()).toBe(403);
  const crossSite = await page.request.post("/api/auth/login", {
    headers: { "sec-fetch-site": "cross-site" },
    data: { email: "editor@publishing.test", password: "EditorDemo2026!" },
  });
  expect(crossSite.status()).toBe(403);
});

test("稿件面板可显隐，移动端可查看并关闭真实稿件", async ({ page }) => {
  await login(page);
  const pane = page.getByRole("complementary", { name: "稿件详情" });
  await expect(pane).toHaveCount(0);
  await page.getByRole("button", { name: "显示稿件面板" }).click();
  await expect(pane).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(pane).toHaveCount(0);
  await page.getByRole("button", { name: "显示稿件面板" }).click();
  await expect(pane).toBeVisible();
  await expect(pane).toContainText("工作台概览");
  await page.getByRole("button", { name: "隐藏稿件面板" }).click();
  await expect(pane).toHaveCount(0);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: /稿件管理/ }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeHidden();
  const data = await (await page.request.get("/api/workspace")).json();
  expect(data.manuscripts.length).toBeGreaterThan(0);
  const manuscript = data.manuscripts[0];
  await page.getByRole("button").filter({ hasText: manuscript.id.slice(0, 8).toUpperCase() }).first().click();
  await expect(page.getByTestId("manuscript-detail")).toContainText(manuscript.title);
  await page.screenshot({ path: "artifacts/hermes-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "关闭稿件详情" }).click();
  await expect(page.getByTestId("manuscript-detail")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});


test("真实对话新建、切换、搜索、刷新及用户隔离", async ({ page }) => {
  await login(page);
  async function createConversation() {
    const created = page.waitForResponse(response => response.url().endsWith("/api/conversations") && response.request().method() === "POST");
    await page.getByRole("button", { name: "新对话", exact: true }).click();
    const response = await created;
    expect(response.status()).toBe(200);
    const conversation = await response.json();
    await expect(page.locator(`[data-conversation-id="${conversation.id}"]`)).toHaveAttribute("aria-current", "true");
    return conversation.id as string;
  }
  const first = await createConversation();
  await page.getByLabel("对话指令", { exact: true }).fill(command);
  const executed = page.waitForResponse(response => response.url().endsWith("/api/conversations/commands") && response.request().method() === "POST");
  await page.getByRole("button", { name: "发送指令" }).click();
  const result = await (await executed).json();
  expect(result.conversation_id).toBe(first);
  const marker = result.manuscript.id.slice(0, 8).toUpperCase();
  await expect(page.getByLabel("对话记录")).toContainText(marker);
  const second = await createConversation();
  expect(second).not.toBe(first);
  await expect(page.getByLabel("对话记录")).not.toContainText(marker);
  await expect(page.getByRole("complementary", { name: "稿件详情" })).toHaveCount(0);
  await page.getByLabel("对话指令", { exact: true }).fill("尚未发送的第二个会话草稿");
  await page.locator(`[data-conversation-id="${first}"]`).click();
  await expect(page.getByLabel("对话记录")).toContainText(marker);
  await expect(page.getByLabel("对话指令", { exact: true })).toHaveValue("");
  await page.screenshot({ path: "artifacts/hermes-desktop-chat.png", fullPage: true });
  await page.locator(`[data-conversation-id="${second}"]`).click();
  await expect(page.getByLabel("对话指令", { exact: true })).toHaveValue("尚未发送的第二个会话草稿");
  await page.locator(`[data-conversation-id="${first}"]`).click();
  await page.getByLabel("全局搜索").fill("不存在的会话标题");
  const searchResults = page.getByRole("region", { name: "搜索结果", exact: true });
  await expect(searchResults.getByText("没有找到相关结果。", { exact: true })).toBeVisible();
  await page.getByLabel("全局搜索").fill("测试稿件初筛");
  await expect(searchResults.locator(`a[href="/?conversation=${first}"]`)).toBeVisible();
  await expect(searchResults.locator(`a[href="/?conversation=${second}"]`)).toHaveCount(0);
  await page.getByLabel("全局搜索").clear();
  await page.reload();
  await expect(page.getByLabel("对话记录")).toContainText(marker);
  const restored = await (await page.request.get(`/api/workspace?conversation_id=${first}`)).json();
  expect(restored.active_conversation_id).toBe(first);
  expect(restored.messages.some((item: { manuscript_id: string | null }) => item.manuscript_id === result.manuscript.id)).toBe(true);
  const emptyConversation = await (await page.request.get(`/api/workspace?conversation_id=${second}`)).json();
  expect(emptyConversation.active_conversation_id).toBe(second);
  expect(emptyConversation.messages).toEqual([]);
  await page.locator(`[data-conversation-id="${second}"]`).click();
  await expect(page.getByLabel("对话记录")).not.toContainText(marker);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("button", { name: "进入工作台", exact: true })).toBeVisible();
  await login(page, "author");
  await expect(page.locator(`[data-conversation-id="${first}"]`)).toHaveCount(0);
  expect((await page.request.get(`/api/workspace?conversation_id=${first}`)).status()).toBe(404);
});

test("邮箱绑定真实 Mailpit 验证、持久化、断开及 Gmail 缺少凭据", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(page.getByText("真实邮件发送已禁用", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "保存邮箱", exact: true }).click();
  await expect(page.getByText("请输入有效邮箱地址", { exact: true })).toBeVisible();
  await expect(page.getByLabel("邮箱地址", { exact: true })).toBeFocused();
  const address = `mailpit-${crypto.randomUUID().slice(0, 8)}@publishing.test`;
  await page.getByLabel("邮箱地址", { exact: true }).fill(address);
  await page.getByLabel("显示名称", { exact: true }).fill("本地测试邮箱");
  await page.getByRole("button", { name: "使用本地 Mailpit" }).click();
  const saved = page.waitForResponse(response => response.url().endsWith("/api/mail/accounts") && response.request().method() === "POST");
  await page.getByRole("button", { name: "保存邮箱", exact: true }).click();
  const savedResponse = await saved;
  expect(savedResponse.ok()).toBe(true);
  const account = await savedResponse.json();
  expect(account.credentials_configured).toBe(false);
  const row = page.getByTestId("mail-account").filter({ hasText: address });
  await expect(row).toContainText("尚未验证");
  const verified = page.waitForResponse(response => response.url().endsWith(`/api/mail/accounts/${account.id}/verify`));
  await row.getByRole("button", { name: "验证连接", exact: true }).click();
  const verifiedAccount = await (await verified).json();
  expect(verifiedAccount.status).toBe("verified");
  await expect(row).toContainText("已验证");
  await page.reload();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(row).toContainText("已验证");
  await row.getByRole("button", { name: "断开连接", exact: true }).click();
  await expect(row).toContainText("已断开");
  await expect(row.getByRole("button", { name: "验证连接", exact: true })).toBeDisabled();
  const rebound = page.waitForResponse(response => response.url().endsWith("/api/mail/accounts") && response.request().method() === "POST");
  await page.getByLabel("邮箱地址", { exact: true }).fill(address);
  await page.getByLabel("显示名称", { exact: true }).fill("重新绑定的本地邮箱");
  await page.getByRole("button", { name: "使用本地 Mailpit" }).click();
  await page.getByRole("button", { name: "保存邮箱", exact: true }).click();
  expect((await (await rebound).json()).id).toBe(account.id);
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("尚未验证");
  await row.getByRole("button", { name: "断开连接", exact: true }).click();
  await expect(row).toContainText("已断开");
  await page.getByLabel("服务商", { exact: true }).selectOption("gmail");
  const gmail = `missing-${crypto.randomUUID().slice(0, 8)}@gmail.com`;
  await page.getByLabel("邮箱地址", { exact: true }).fill(gmail);
  await page.getByLabel("显示名称", { exact: true }).fill("待配置 Gmail");
  await page.getByLabel("凭据引用", { exact: true }).fill(`E2E_${crypto.randomUUID().replaceAll("-", "").slice(0, 20).toUpperCase()}`);
  await page.getByRole("button", { name: "保存邮箱", exact: true }).click();
  const gmailRow = page.getByTestId("mail-account").filter({ hasText: gmail });
  await expect(gmailRow).toContainText("凭据未配置");
  await gmailRow.getByRole("button", { name: "验证连接", exact: true }).click();
  await expect(gmailRow).toContainText("需要凭据");
  await expect(gmailRow).not.toContainText("已验证");
  await page.getByRole("heading", { name: "邮箱", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "artifacts/mail-settings.png", fullPage: true });
  await page.getByText("服务器配置指南", { exact: true }).click();
  await expect(page.getByText("MAIL_CREDENTIAL_EDITORIAL_ACCESS_TOKEN", { exact: true })).toBeVisible();
  const persisted = await (await page.request.get("/api/mail/accounts")).json();
  expect(persisted.email_send_enabled).toBe(false);
  expect(persisted.accounts.find((item: {id: string}) => item.id === account.id).status).toBe("disconnected");
  await page.screenshot({ path: "artifacts/mail-setup-guide.png", fullPage: true });
});

test("侧栏收起恢复和移动抽屉键盘与布局", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "收起侧栏" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeHidden();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeHidden();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("button", { name: "关闭导航", exact: true })).toBeFocused();
  await page.screenshot({ path: "artifacts/hermes-mobile-drawer.png", fullPage: true });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeHidden();
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeHidden();
  await expect(page.getByLabel("对话指令", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "稿件详情" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "artifacts/hermes-mobile-chat.png", fullPage: true });
});

async function createRecoveryConversation(page: Page) {
  const created = page.waitForResponse(response => response.url().endsWith("/api/conversations") && response.request().method() === "POST");
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  const response = await created;
  expect(response.status()).toBe(200);
  const conversation = await response.json();
  await expect(page.locator(`[data-conversation-id="${conversation.id}"]`)).toHaveAttribute("aria-current", "true");
  return conversation.id as string;
}

async function sendRecoveryCommand(page: Page) {
  await page.getByLabel("对话指令", { exact: true }).fill(command);
  const executed = page.waitForResponse(response => response.url().endsWith("/api/conversations/commands") && response.request().method() === "POST");
  await page.getByRole("button", { name: "发送指令" }).click();
  const response = await executed;
  expect(response.status()).toBe(200);
  const result = await response.json();
  const marker = result.manuscript.id.slice(0, 8).toUpperCase() as string;
  await expect(page.getByLabel("对话记录")).toContainText(marker);
  return marker;
}

function recoveryGate() {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
}

test("会话切换请求未完成时刷新仍恢复点击的目标会话", async ({ page }) => {
  await login(page);
  const first = await createRecoveryConversation(page);
  const marker = await sendRecoveryCommand(page);
  const second = await createRecoveryConversation(page);
  await expect(page.getByLabel("对话记录")).not.toContainText(marker);
  expect(new URL(page.url()).searchParams.get("conversation")).toBe(second);

  const requested = recoveryGate();
  const pending = recoveryGate();
  let requests = 0;
  await page.route(`**/api/workspace?conversation_id=${first}`, async route => {
    requests++;
    if (requests === 1) {
      requested.release();
      await pending.promise;
      return route.abort("aborted");
    }
    return route.continue();
  });

  try {
    await page.locator(`[data-conversation-id="${first}"]`).click();
    await requested.promise;
    // The target must be persisted before the held response can commit UI state.
    expect(new URL(page.url()).searchParams.get("conversation")).toBe(first);
    await expect(page.locator(`[data-conversation-id="${first}"]`)).toBeDisabled();
    await page.reload();
    await expect(page.locator(`[data-conversation-id="${first}"]`)).toHaveAttribute("aria-current", "true");
    await expect(page.getByLabel("对话记录")).toContainText(marker);
    expect(new URL(page.url()).searchParams.get("conversation")).toBe(first);
    expect(requests).toBeGreaterThan(1);
  } finally {
    pending.release();
  }
});

test("会话切换失败恢复原URL、消息和草稿，随后可成功重试", async ({ page }) => {
  await login(page);
  const first = await createRecoveryConversation(page);
  const second = await createRecoveryConversation(page);
  const marker = await sendRecoveryCommand(page);
  const draft = "切换失败后应保留的第二会话草稿";
  await page.getByLabel("对话指令", { exact: true }).fill(draft);

  const requested = recoveryGate();
  const failed = recoveryGate();
  let requests = 0;
  await page.route(`**/api/workspace?conversation_id=${first}`, async route => {
    requests++;
    if (requests === 1) {
      requested.release();
      await failed.promise;
      return route.fulfill({ status: 500, json: { detail: "合成会话切换故障" } });
    }
    return route.continue();
  });

  try {
    await page.locator(`[data-conversation-id="${first}"]`).click();
    await requested.promise;
    expect(new URL(page.url()).searchParams.get("conversation")).toBe(first);
    failed.release();
    await expect(page.getByRole("alert").filter({ hasText: "合成会话切换故障" })).toBeVisible();
    await expect(page.locator(`[data-conversation-id="${first}"]`)).toBeEnabled();
    expect(new URL(page.url()).searchParams.get("conversation")).toBe(second);
    await expect(page.locator(`[data-conversation-id="${second}"]`)).toHaveAttribute("aria-current", "true");
    await expect(page.getByLabel("对话记录")).toContainText(marker);
    await expect(page.getByLabel("对话指令", { exact: true })).toHaveValue(draft);

    await page.locator(`[data-conversation-id="${first}"]`).click();
    await expect(page.locator(`[data-conversation-id="${first}"]`)).toHaveAttribute("aria-current", "true");
    expect(new URL(page.url()).searchParams.get("conversation")).toBe(first);
    await expect(page.getByLabel("对话记录")).not.toContainText(marker);
    await expect(page.getByLabel("对话指令", { exact: true })).toHaveValue("");
    await expect(page.getByRole("alert").filter({ hasText: "合成会话切换故障" })).toHaveCount(0);
    expect(requests).toBe(2);

    await page.locator(`[data-conversation-id="${second}"]`).click();
    await expect(page.getByLabel("对话记录")).toContainText(marker);
    await expect(page.getByLabel("对话指令", { exact: true })).toHaveValue(draft);
  } finally {
    failed.release();
  }
});
