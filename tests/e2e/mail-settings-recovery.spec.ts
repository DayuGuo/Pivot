import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

type SavedAccount = { id: string; address: string; provider: string; smtp_host: string; smtp_port: number; auth_mode: string };

async function login(page: Page) {
  const health = await (await page.request.get("/api/health")).json();
  expect(health.editorial_model.provider).toBe("mock");
  const response = await page.request.post("/api/auth/login", {
    data: { email: "editor@publishing.test", password: "EditorDemo2026!" },
  });
  expect(response.status()).toBe(200);
  return await (await page.request.get("/api/publishing/session")).json();
}

async function openMail(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const panel = page.getByRole("dialog", { name: "设置", exact: true });
  await expect(panel.getByRole("heading", { name: "模型 API", exact: true })).toBeVisible();
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeEnabled();
  await expect(panel.getByText("真实邮件发送已禁用", { exact: true })).toBeVisible();
  return panel;
}

test("邮箱恢复：真实 Mailpit 配置已提交但回执丢失，主动读取恢复唯一账户（UI 网络夹具）", async ({ page }) => {
  test.info().annotations.push({ type: "fixture", description: "登录、会话、账户写入和读取均为真实 Mock 隔离 API；只在 POST 已成功提交后丢弃其浏览器回执，不调用邮件发送。" });
  await login(page);
  const panel = await openMail(page);
  const address = `lost-receipt-${randomUUID()}@publishing.test`;
  const writes: string[] = [];
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path.startsWith("/api/mail/")) writes.push(path);
  });
  let committed: SavedAccount | undefined;
  let accountReads = 0;
  await page.route("**/api/mail/accounts", async route => {
    if (route.request().method() !== "POST") { accountReads++; await route.continue(); return; }
    // The server commits a real Mailpit binding before this UI-only network failure.
    const response = await route.fetch({ maxRedirects: 0, maxRetries: 0 });
    expect(response.status()).toBe(200);
    committed = await response.json();
    await route.abort("failed");
  });
  await panel.getByLabel("邮箱地址", { exact: true }).fill(address);
  await panel.getByLabel("显示名称", { exact: true }).fill("回执丢失的本地 Mailpit 配置");
  await panel.getByRole("button", { name: "使用本地 Mailpit", exact: true }).click();
  await panel.getByRole("button", { name: "保存邮箱", exact: true }).click();
  const unknown = panel.getByText("上次操作结果尚未确认。请先重新读取邮箱并核对服务端记录；本页不会自动重发。", { exact: true });
  await expect(unknown).toBeVisible();
  expect(committed).toMatchObject({ address, provider: "smtp", smtp_host: "mailpit", smtp_port: 1025, auth_mode: "none" });
  expect(writes).toEqual(["/api/mail/accounts"]);
  expect(accountReads).toBe(0);
  await expect(panel.getByText("邮箱配置已保存，请验证连接。", { exact: true })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeDisabled();
  await expect(panel.getByLabel("邮箱地址", { exact: true })).toBeDisabled();
  const accountActions = panel.getByRole("button", { name: /^(验证连接|断开连接)$/ });
  const accountActionCount = await accountActions.count();
  expect(accountActionCount).toBeGreaterThan(0);
  await expect.poll(() => accountActions.evaluateAll(buttons => ({
    count: buttons.length,
    disabled: buttons.filter(button => button.matches(":disabled")).length,
  }))).toEqual({ count: accountActionCount, disabled: accountActionCount });
  await panel.getByRole("tab", { name: "模型 API", exact: true }).click();
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(unknown).toBeVisible();
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeDisabled();
  expect(writes).toEqual(["/api/mail/accounts"]);
  expect(accountReads).toBe(0);

  await panel.getByRole("button", { name: "重新读取邮箱", exact: true }).click();
  const row = panel.getByTestId("mail-account").filter({ hasText: address });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("尚未验证");
  await expect(panel.getByText("邮箱状态已重新读取，请核对服务端记录后决定是否继续。", { exact: true })).toBeVisible();
  await expect(unknown).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "保存邮箱", exact: true })).toBeEnabled();
  expect(accountReads).toBe(1);
  expect(writes).toEqual(["/api/mail/accounts"]);
  const persisted = await (await page.request.get("/api/mail/accounts")).json();
  expect(persisted.email_send_enabled).toBe(false);
  const matches = persisted.accounts.filter((item: SavedAccount) => item.address === address);
  expect(matches).toHaveLength(1);
  expect(matches[0].id).toBe(committed?.id);
});

test("邮箱权限：GET 403 清除旧账户与待保存表单，切换分类不能重新写入（UI 权限夹具）", async ({ page }) => {
  test.info().annotations.push({ type: "fixture", description: "使用真实编辑登录和真实 Mailpit 账户；仅拦截浏览器 GET /api/mail/accounts 返回 403，验证客户端撤权处理，不声称服务端角色已改变。" });
  const session = await login(page);
  const address = `denied-read-${randomUUID()}@publishing.test`;
  const saved = await page.request.post("/api/mail/accounts", {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { provider: "smtp", address, display_name: "403 前的真实 Mailpit 账户", smtp_host: "mailpit", smtp_port: 1025, tls_mode: "none", auth_mode: "none" },
  });
  expect(saved.status()).toBe(200);
  const account = await saved.json();
  const panel = await openMail(page);
  await expect(panel.getByTestId("mail-account").filter({ hasText: address })).toHaveCount(1);
  await panel.getByLabel("邮箱地址", { exact: true }).fill(`unsaved-${randomUUID()}@publishing.test`);
  await panel.getByLabel("显示名称", { exact: true }).fill("权限撤回后不得保留的草稿");
  await panel.getByLabel("SMTP 主机", { exact: true }).fill("smtp.synthetic.invalid");
  await panel.getByLabel("SMTP 用户名", { exact: true }).fill("synthetic-unsaved-user");
  await panel.getByLabel("凭据引用", { exact: true }).fill("SYNTHETIC_UNSAVED");
  const writes: string[] = [];
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path.startsWith("/api/mail/")) writes.push(path);
  });
  let deniedReads = 0;
  await page.route("**/api/mail/accounts", async route => {
    if (route.request().method() === "GET") {
      deniedReads++;
      await route.fulfill({ status: 403, json: { detail: "UI 夹具：邮箱访问权限已撤销" } });
    } else await route.continue();
  });
  await panel.getByRole("button", { name: "重新读取邮箱", exact: true }).click();
  const denied = panel.getByRole("alert").filter({ hasText: "当前身份无权访问邮箱设置。" });
  await expect(denied).toBeVisible();
  await expect(denied).toBeFocused();
  await expect(panel.getByTestId("mail-account")).toHaveCount(0);
  await expect(panel.getByText(address, { exact: true })).toHaveCount(0);
  await expect(panel.locator("input, select")).toHaveCount(0);
  for (const name of ["保存邮箱", "验证连接", "断开连接"]) await expect(panel.getByRole("button", { name, exact: true })).toHaveCount(0);
  await expect(panel.getByText("服务器配置指南", { exact: true })).toHaveCount(0);
  await page.keyboard.press("Enter");
  await panel.getByRole("tab", { name: "模型 API", exact: true }).click();
  await panel.getByRole("tab", { name: "邮箱", exact: true }).click();
  await expect(denied).toBeVisible();
  await expect(panel.getByTestId("mail-account")).toHaveCount(0);
  await expect(panel.locator("input, select")).toHaveCount(0);
  expect(deniedReads).toBe(1);
  expect(writes).toEqual([]);
  // Page.request bypasses the browser-only 403 fixture: it confirms no destructive write occurred.
  const persisted = await (await page.request.get("/api/mail/accounts")).json();
  expect(persisted.email_send_enabled).toBe(false);
  expect(persisted.accounts.filter((item: SavedAccount) => item.id === account.id)).toHaveLength(1);
});
