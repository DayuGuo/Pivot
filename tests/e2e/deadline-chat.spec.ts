import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

test.use({ timezoneId: "America/Los_Angeles" });
const chatURL = /\/api\/publishing\/chat$/;
async function login(page: Page) {
  const health = await page.request.get("/api/health");
  expect((await health.json()).editorial_model.provider).toBe("mock");
  const r = await page.request.post("/api/auth/login", { data: { email: "author@publishing.test", password: "AuthorDemo2026!" } });
  expect(r.status()).toBe(200);
  return r.json();
}
async function draft(page: Page, csrf: string) {
  const r = await page.request.post("/api/publishing/drafts", { headers: { "X-CSRF-Token": csrf }, data: { request_id: randomUUID(), title: `完全合成期限问答 ${randomUUID().slice(0, 8)}` } });
  expect(r.status()).toBe(200);
  return (await r.json()).manuscript_id as string;
}
async function send(page: Page, text: string) {
  await page.getByRole("textbox", { name: "向出版助手发送消息" }).fill(text);
  const response = page.waitForResponse(r => chatURL.test(r.url()) && r.request().method() === "POST");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  const r = await response;
  expect(r.status()).toBe(200);
  return r.json();
}

test("真实待办问答：当前稿件、浏览器时区、刷新和引用", async ({ page }) => {
  const auth = await login(page);
  const mid = await draft(page, auth.csrf_token);
  await page.goto(`/publishing?manuscript=${mid}`);
  const result = await send(page, "所有待办");
  const message = result.messages[1], snapshot = message.work_snapshot;
  expect(result.state_changed).toBe(false);
  expect(message.provider).toBe("records");
  expect(snapshot.timezone).toBe("America/Los_Angeles");
  expect(snapshot.items).toHaveLength(1);
  expect(snapshot.items[0].manuscript_id).toBe(mid);
  await expect(page.getByText(message.content, { exact: true })).toBeVisible();
  await expect(page.getByText("工作记录", { exact: true })).toBeVisible();
  const reference = page.getByRole("link", { name: message.references[0].label, exact: true }).last();
  await expect(reference).toHaveAttribute("href", `/publishing?manuscript=${mid}`);
  await page.reload();
  await expect(page.getByText(message.content, { exact: true })).toBeVisible();
  const current = await page.request.get(`/api/publishing/manuscripts/${mid}`);
  expect((await current.json()).stage).toBe("author_draft");
});

test("真实今日查询与日历同一日期范围、组合请求不能发信或决定", async ({ page }) => {
  await login(page);
  await page.goto("/publishing");
  const result = await send(page, "今天有哪些到期任务？列出即可，不要发送邮件或作出录用决定");
  expect(result.state_changed).toBe(false);
  const message = result.messages[1], snapshot = message.work_snapshot;
  expect(message.action).toBeNull();
  const local = new Intl.DateTimeFormat("en-CA", { timeZone: snapshot.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(snapshot.read_at));
  const r = await page.request.get(`/api/calendar?month=${local.slice(0, 7)}&day=${local}&tz=${encodeURIComponent(snapshot.timezone)}`);
  expect(r.status()).toBe(200);
  const calendar = await r.json();
  expect(snapshot.items.map((x: { id: string }) => x.id)).toEqual(calendar.items.map((x: { id: string }) => x.id));
  await expect(page.getByText(message.content, { exact: true })).toBeVisible();
});

test("真实分页：自然语言继续、刷新保留、零重复", async ({ page }) => {
  const auth = await login(page);
  for (let i = 0; i < 13; i++) await draft(page, auth.csrf_token);
  await page.goto("/publishing");
  const first = (await send(page, "所有待办")).messages[1].work_snapshot;
  expect(first.items).toHaveLength(12);
  expect(first.total).toBeGreaterThanOrEqual(13);
  expect(first.next_cursor).toBeTruthy();
  await expect(page.getByRole("textbox", { name: "向出版助手发送消息" })).toHaveValue("");
  await page.reload();
  const second = (await send(page, "继续查看待办")).messages[1].work_snapshot;
  expect(second.read_at).toBe(first.read_at);
  expect(second.cursor).toBe(first.next_cursor);
  const seen = new Set(first.items.map((x: { id: string }) => x.id));
  expect(second.items.every((x: { id: string }) => !seen.has(x.id))).toBe(true);
});
