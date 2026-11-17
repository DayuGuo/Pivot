import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

// Actual local Mock authentication and private dossier APIs. The private-profile
// landing hint is injected only in marked cases; backend profile policy has API tests.
async function authenticate(page: Page, role: "editor" | "author" = "editor") {
  const response = await page.request.post("/api/auth/login", { data: {
    email: `${role}@publishing.test`,
    password: role === "author" ? "AuthorDemo2026!" : "EditorDemo2026!",
  } });
  expect(response.status()).toBe(200);
  return response.json() as Promise<{ csrf_token: string }>;
}

async function submitLogin(page: Page, role: "editor" | "author" = "editor") {
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}@publishing.test`);
  await page.getByLabel("密码", { exact: true }).fill(role === "author" ? "AuthorDemo2026!" : "EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
}

async function landingHint(page: Page, value: string) {
  await page.route(/\/api\/auth\/(login|me)$/, async route => {
    const response = await route.fetch();
    if (!response.ok()) { await route.fulfill({ response }); return; }
    await route.fulfill({ response, json: { ...await response.json(), landing_path: value } });
  });
}

test("资料登录入口用固定返回目标，登录后仍打开本人同一资料", async ({ page, context }) => {
  const session = await authenticate(page);
  const title = `试用入口合成资料 ${randomUUID()}`;
  const response = await page.request.post("/api/dossiers", {
    headers: { "X-CSRF-Token": session.csrf_token }, data: {
      request_id: randomUUID(), title, source_kind: "synthetic",
      source_note: "试用入口浏览器测试生成的合成资料，无真实作者数据。", authorized_material: true,
    },
  });
  expect(response.status()).toBe(200);
  const id = (await response.json()).dossier_id;
  await context.clearCookies();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/library?dossier=${id}`);
  const back = page.getByRole("link", { name: "返回登录", exact: true });
  await expect(back).toHaveAttribute("href", `/?entry=library&dossier=${id}`);
  await back.focus(); await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`entry=library&dossier=${id}$`));
  await submitLogin(page);
  await expect(page).toHaveURL(new RegExp(`/library\\?dossier=${id}$`));
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue(title);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("私人版登录落点提示直接进入资料，跳过旧工作台读取", async ({ page }) => {
  await landingHint(page, "/library");
  const oldWorkspace: string[] = [];
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/api/workspace") oldWorkspace.push(request.url());
  });
  await page.goto("/");
  await submitLogin(page);
  await expect(page).toHaveURL(/\/library(?:\?|$)/);
  await expect(page.getByRole("button", { name: "新建资料", exact: true }).first()).toBeVisible();
  expect(oldWorkspace).toEqual([]);
});

test("私人版恢复登录仍优先打开显式旧对话深链", async ({ page }) => {
  const session = await authenticate(page);
  const response = await page.request.post("/api/conversations", {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { title: `试用入口旧对话 ${randomUUID()}` },
  });
  expect(response.status()).toBe(200);
  const conversation = await response.json();
  await landingHint(page, "/library");
  await page.goto(`/?conversation=${conversation.id}`);
  await expect(page.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`conversation=${conversation.id}$`));
  await page.goto("/");
  await expect(page).toHaveURL(/\/library(?:\?|$)/);
  await expect(page.getByRole("button", { name: "新建资料", exact: true }).first()).toBeVisible();
});

test("入口参数与服务器未知落点都不能跳到外站，本地默认仍保留旧工作台", async ({ page }) => {
  await landingHint(page, "https://example.invalid/collect");
  await page.goto("/?entry=https%3A%2F%2Fexample.invalid&next=%2F%2Fexample.invalid");
  await submitLogin(page);
  await expect(page.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  await page.goto("/?entry=library&dossier=%2F%2Fexample.invalid");
  await expect(page).toHaveURL(/\/library(?:\?|$)/);
  expect(new URL(page.url()).searchParams.get("dossier")).not.toBe("//example.invalid");
});

test("作者不能借资料入口或伪造落点获得编辑资料权限", async ({ page }) => {
  await landingHint(page, "/library");
  await page.goto("/?entry=library");
  await submitLogin(page, "author");
  await expect(page.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  const forbidden = await page.request.get("/api/dossiers");
  expect(forbidden.status()).toBe(403);
});
