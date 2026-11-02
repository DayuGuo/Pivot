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
  await expect(pane).toBeVisible();
  await page.getByRole("button", { name: "隐藏稿件面板" }).click();
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
  await page.getByRole("navigation").getByRole("button", { name: /稿件管理/ }).click();
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
