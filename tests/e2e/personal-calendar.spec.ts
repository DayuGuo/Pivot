import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

test.use({ timezoneId: "UTC" });
const endpoint = /\/api\/calendar(?:\?|$)/;
const calendar = (page: Page) => page.getByRole("region", { name: "个人日历", exact: true });
type Item = { id: string; manuscript_id: string; number: string; title: string; kind: string; label: string; status: string; due_at: string; overdue: boolean; href: string };
async function login(page: Page, role = "editor") {
  const health = await page.request.get("/api/health");
  expect((await health.json()).editorial_model.provider).toBe("mock");
  const auth = await page.request.post("/api/auth/login", { data: { email: `${role}@publishing.test`, password: role === "author" ? "AuthorDemo2026!" : "EditorDemo2026!" } });
  expect(auth.status()).toBe(200);
  return auth.json();
}
function item(title: string, month: string): Item {
  const id = randomUUID(), manuscript_id = randomUUID();
  return { id, manuscript_id, number: "SYNTHETIC-CALENDAR", title, kind: "precheck_completeness", label: "资料完整性检查", status: "pending", due_at: `${month}-15T12:00:00+00:00`, overdue: false, href: `/publishing?manuscript=${manuscript_id}` };
}
function payload(url: string, items: Item[] = [], next_cursor: string | null = null, count = items.length) {
  const q = new URL(url).searchParams, month = q.get("month")!;
  return { month, timezone: q.get("tz"), view: q.get("view"), day: q.get("day"), server_now: new Date().toISOString(), days: count ? [{ date: `${month}-15`, count }] : [], counts: { month: count, overdue: 0, undated: 0 }, items, next_cursor };
}
async function open(page: Page) {
  await calendar(page).getByRole("button", { name: "日历", exact: true }).click();
}
async function draft(page: Page, csrf: string, title: string) {
  const response = await page.request.post("/api/publishing/drafts", { headers: { "X-CSRF-Token": csrf }, data: { request_id: randomUUID(), title } });
  expect(response.status()).toBe(200); return (await response.json()).manuscript_id as string;
}

test("四个真实工作区日历展开后底部身份保持可见", async ({ page }) => {
  await login(page);
  for (const path of ["/", "/publishing", "/library", "/workbench"]) {
    await page.goto(path);
    const button = calendar(page).getByRole("button", { name: "日历", exact: true });
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    const search = await page.getByRole("searchbox", { name: "全局搜索" }).boundingBox();
    const box = await button.boundingBox();
    expect(box!.y).toBeGreaterThan(search!.y + search!.height);
    expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
    await open(page);
    await expect(calendar(page).getByRole("button", { name: /^本月 \d/ })).toBeVisible();
    await expect(page.locator('summary[aria-label="切换身份"]')).toBeInViewport({ ratio: 1 });
    await expect(calendar(page).locator("button[data-date]").last()).toBeInViewport({ ratio: 1 });
    for (const name of [/^本月 \d/, /^逾期 \d/, /^今天$/]) await expect(calendar(page).getByRole("button", { name })).toBeInViewport({ ratio: 1 });
  }
});

test("真实作者待办按日期查询、定位稿件且刷新后保留", async ({ page, browserName }) => {
  const auth = await login(page, "author");
  const id = await draft(page, auth.csrf_token, `完全合成日历验收 ${randomUUID().slice(0, 8)}`);
  const workspace = await page.request.get(`/api/publishing/workspace?role_view=true`);
  const task = (await workspace.json()).tasks.find((x: { manuscript_id: string }) => x.manuscript_id === id);
  expect(task).toBeTruthy();
  const month = task.due_at.slice(0, 7);
  const response = await page.request.get(`/api/calendar?month=${month}&tz=UTC`);
  expect(response.status()).toBe(200);
  const current = (await response.json()).items[0] as Item;
  expect(current).toBeTruthy();
  await page.goto("/publishing"); await open(page);
  // Usually the current month; follow native month navigation if the new deadline crosses it.
  const currentMonth = new Date().toISOString().slice(0, 7);
  if (month !== currentMonth) await calendar(page).getByRole("button", { name: "下个月" }).click();
  const link = calendar(page).getByRole("link").filter({ hasText: current.title }).first();
  await expect(link).toHaveAttribute("href", current.href);
  await expect(page.getByText("正在载入当前对话…", { exact: true })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ animations: "disabled", path: `artifacts/calendar/${browserName}-desktop.png` });
  await link.click(); await expect(page).toHaveURL(new RegExp(`manuscript=${current.manuscript_id}`));
  await expect(page.getByRole("region", { name: "出版助手" })).toBeVisible();
  await page.reload(); await open(page);
  await expect(calendar(page).getByRole("button", { name: "逾期", exact: false })).toBeVisible();
  const persisted = await page.request.get(`/api/publishing/manuscripts/${current.manuscript_id}`);
  expect(persisted.status()).toBe(200);
});

test("UI fixture：切月的迟到响应不会覆盖当前月份", async ({ page }) => {
  await login(page);
  let release!: () => void, observed!: () => void;
  const held = new Promise<void>(r => { release = r; });
  const seen = new Promise<void>(r => { observed = r; });
  let requests = 0;
  await page.route(endpoint, async route => {
    const n = ++requests, url = route.request().url(), month = new URL(url).searchParams.get("month")!;
    if (n === 1) { observed(); await held; }
    await route.fulfill({ json: payload(url, [item(n === 1 ? "迟到月份旧任务" : "当前月份任务", month)]) });
  });
  try {
    await page.goto("/publishing"); await open(page); await seen;
    await calendar(page).getByRole("button", { name: "下个月" }).click();
    await expect(calendar(page).getByText("当前月份任务", { exact: true })).toBeVisible();
    release();
    await expect(calendar(page).getByText("迟到月份旧任务", { exact: true })).toHaveCount(0);
    expect(requests).toBe(2);
  } finally { release(); }
});

for (const status of [401, 403]) test(`UI fixture：${status}清除旧日历且重新展开不重发`, async ({ page }) => {
  await login(page); let calls = 0;
  await page.route(endpoint, async route => {
    calls++; const url = route.request().url(), month = new URL(url).searchParams.get("month")!;
    await route.fulfill(calls === 1 ? { json: payload(url, [item("旧权限日历任务", month)]) } : { status, json: { detail: "Access denied" } });
  });
  await page.goto("/publishing"); await open(page);
  await expect(calendar(page).getByText("旧权限日历任务", { exact: true })).toBeVisible();
  await calendar(page).getByRole("button", { name: "下个月" }).click();
  await expect(calendar(page).getByRole("alert")).toContainText("身份已失效");
  await expect(calendar(page).getByText("旧权限日历任务", { exact: true })).toHaveCount(0);
  await open(page); await open(page);
  await expect(calendar(page).getByRole("link", { name: "重新打开工作区" })).toBeVisible();
  expect(calls).toBe(2);
});

test("UI fixture：拒绝未知链接并显式恢复，不执行写请求", async ({ page }) => {
  await login(page); let calls = 0;
  await page.route(endpoint, async route => {
    expect(route.request().method()).toBe("GET"); calls++;
    const url = route.request().url(), month = new URL(url).searchParams.get("month")!;
    const target = item("安全的当前任务", month);
    if (calls === 1) target.href = "https://untrusted.invalid/";
    await route.fulfill({ json: payload(url, [target]) });
  });
  await page.goto("/publishing"); await open(page);
  await expect(calendar(page).getByRole("alert")).toContainText("日历目标无效");
  await expect(calendar(page).locator("a[href^='https:']")).toHaveCount(0);
  await calendar(page).getByRole("button", { name: "重新载入" }).click();
  await expect(calendar(page).getByText("安全的当前任务", { exact: true })).toBeVisible();
  expect(calls).toBe(2);
});

test("UI fixture：日期键盘、空日期、分页和390px原生日期选择", async ({ page, browserName }) => {
  await login(page);
  await page.route(endpoint, async route => {
    const url = route.request().url(), q = new URL(url).searchParams, month = q.get("month")!;
    if (q.get("view") === "overdue") {
      const rows = [new Date().getUTCFullYear() - 2, new Date().getUTCFullYear() - 1].map(year => ({ ...item(`合成逾期${year}`, `${year}-06`), overdue: true }));
      const result = payload(url, rows, null, 0); result.counts.overdue = rows.length;
      return route.fulfill({ json: result });
    }
    const items = q.get("day") && !q.get("day")!.endsWith("-15") ? [] : [item(q.has("cursor") ? "第二页任务" : "第一页任务", month)];
    await route.fulfill({ json: payload(url, items, q.has("cursor") || q.has("day") ? null : "next-page", items.length ? 2 : 0) });
  });
  await page.goto("/publishing"); await open(page);
  await expect(calendar(page).getByText("第一页任务", { exact: true })).toBeVisible();
  await calendar(page).getByRole("button", { name: /^逾期/ }).click();
  for (const year of [new Date().getUTCFullYear() - 2, new Date().getUTCFullYear() - 1]) await expect(calendar(page).getByRole("link").filter({ hasText: `合成逾期${year}` }).locator("time")).toContainText(`${year}年`);
  // Native Tab navigation scrolls real task links into view on WebKit too.
  await calendar(page).getByRole("button", { name: /^逾期/ }).focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("Tab");
  await expect(calendar(page).getByRole("link").filter({ hasText: `合成逾期${new Date().getUTCFullYear() - 1}` })).toBeFocused();
  for (const stamp of await calendar(page).locator("time").all()) await expect(stamp).toBeInViewport({ ratio: 1 });
  expect(await calendar(page).evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.evaluate(() => document.fonts.ready);
  const crop = await calendar(page).boundingBox(); expect(crop).not.toBeNull();
  await page.screenshot({ animations: "disabled", clip: crop!, path: `artifacts/calendar/${browserName}-overdue-years.png` });
  await calendar(page).getByRole("button", { name: /^本月/ }).click();
  await expect(calendar(page).getByText("第一页任务", { exact: true })).toBeVisible();
  const button = calendar(page).getByRole("button", { name: /^\d{4}-\d{2}-15，/ });
  await button.focus(); await page.keyboard.press("ArrowRight");
  await expect(calendar(page).locator("button[data-date$='-16']")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(calendar(page).getByText("这天没有截止任务。", { exact: true })).toBeVisible();
  await calendar(page).getByRole("button", { name: /^本月/ }).click();
  await calendar(page).getByRole("button", { name: "继续查看" }).click();
  await expect(calendar(page).getByText("第一页任务", { exact: true })).toBeVisible();
  await expect(calendar(page).getByText("第二页任务", { exact: true })).toBeVisible();
  if (browserName === "chromium") { await page.emulateMedia({ colorScheme: "dark" }); await expect(calendar(page).getByRole("button", { name: "日历", exact: true })).toHaveCSS("color", "rgb(231, 233, 239)"); await page.screenshot({ animations: "disabled", path: "artifacts/calendar/chromium-dark.png" }); }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "打开工作列表", exact: true }).click();
  const date = calendar(page).getByLabel("截止日期", { exact: true });
  await expect(date).toBeVisible();
  const month = new Date().toISOString().slice(0, 7);
  await date.fill(`${month}-16`);
  await expect(calendar(page).getByText("这天没有截止任务。", { exact: true })).toBeVisible();
  await page.screenshot({ animations: "disabled", path: `artifacts/calendar/${browserName}-mobile.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("日历跳转保留作者未保存表单的离开保护", async ({ page }) => {
  const session = await login(page, "author");
  const first = await draft(page, session.csrf_token, `合成日历保护甲 ${randomUUID().slice(0, 8)}`);
  const secondTitle = `合成日历保护乙 ${randomUUID().slice(0, 8)}`;
  const second = await draft(page, session.csrf_token, secondTitle);
  await page.route(endpoint, async route => {
    const url = route.request().url(), month = new URL(url).searchParams.get("month")!;
    await route.fulfill({ json: payload(url, [{ ...item(secondTitle, month), manuscript_id: second, href: `/publishing?manuscript=${second}` }]) });
  });
  await page.goto(`/publishing?manuscript=${first}`);
  const title = page.getByLabel("标题", { exact: true }); await title.fill("只在浏览器内的合成未保存标题");
  await open(page); const initialURL = page.url();
  const target = calendar(page).getByRole("link").filter({ hasText: secondTitle });
  await expect(target).toBeVisible();
  const dialog = page.waitForEvent("dialog"), click = target.click({ noWaitAfter: true });
  await (await dialog).dismiss(); await click;
  await expect(page).toHaveURL(initialURL);
  await expect(title).toHaveValue("只在浏览器内的合成未保存标题");
  await expect(target).toBeVisible();
});

test("UI fixture：分页422后重新载入首批，不重复无效游标", async ({ page }) => {
  await login(page); let cursorRequests = 0, firstRequests = 0;
  await page.route(endpoint, async route => {
    const url = route.request().url(), q = new URL(url).searchParams;
    if (q.has("cursor")) { cursorRequests++; await route.fulfill({ status: 422, json: { detail: "Cursor invalid" } }); return; }
    firstRequests++;
    await route.fulfill({ json: payload(url, [item("当前授权的首批任务", q.get("month")!)], "outdated-cursor") });
  });
  await page.goto("/publishing"); await open(page);
  await expect(calendar(page).getByText("当前授权的首批任务", { exact: true })).toBeVisible();
  await calendar(page).getByRole("button", { name: "继续查看" }).click();
  await expect(calendar(page).getByRole("alert")).toContainText("分页位置已失效");
  await calendar(page).getByRole("button", { name: "重新载入" }).click();
  await expect(calendar(page).getByText("当前授权的首批任务", { exact: true })).toBeVisible();
  expect(cursorRequests).toBe(1); expect(firstRequests).toBe(2);
});

test.describe("部署时区兼容", () => {
  test.use({ timezoneId: "Asia/Shanghai" });
  test("UI fixture：不支持的浏览器时区经用户显式选择UTC恢复", async ({ page }) => {
    await login(page); const zones: string[] = [];
    await page.route(endpoint, async route => {
      const url = route.request().url(), q = new URL(url).searchParams; zones.push(q.get("tz")!);
      await route.fulfill(q.get("tz") === "UTC" ? { json: payload(url) } : { status: 422, json: { detail: "Timezone unavailable" } });
    });
    await page.goto("/publishing"); await open(page);
    await expect(calendar(page).getByRole("alert")).toContainText("当前时区暂不受支持");
    await calendar(page).getByRole("button", { name: "使用 UTC" }).click();
    await expect(calendar(page).getByLabel("显示时区 UTC", { exact: true })).toBeVisible();
    await expect(calendar(page).getByText("本月没有截止任务。", { exact: true })).toBeVisible();
    expect(zones).toEqual(["Asia/Shanghai", "UTC"]);
  });
});


test("UI fixture：响应头到达后正文停住仍会超时，主动重试恢复", async ({ page }) => {
  await login(page);
  await page.addInitScript(() => {
    const original = window.fetch.bind(window); let stalled = false;
    window.fetch = async (input, init) => {
      if (!stalled && String(input).includes("/api/calendar?")) {
        stalled = true;
        const body = new ReadableStream({ start(controller) {
          const fail = () => controller.error(new DOMException("Aborted", "AbortError"));
          if (init?.signal?.aborted) fail(); else init?.signal?.addEventListener("abort", fail, { once: true });
        } });
        return new Response(body, { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return original(input, init);
    };
  });
  await page.route(endpoint, async route => {
    const url = route.request().url(), month = new URL(url).searchParams.get("month")!;
    await route.fulfill({ json: payload(url, [item("超时后恢复的授权任务", month)]) });
  });
  await page.goto("/publishing"); await open(page);
  await expect(calendar(page).getByRole("alert")).toContainText("无法载入日历", { timeout: 15_000 });
  await expect(calendar(page).getByText("正在载入…", { exact: true })).toHaveCount(0);
  await calendar(page).getByRole("button", { name: "重新载入" }).click();
  await expect(calendar(page).getByText("超时后恢复的授权任务", { exact: true })).toBeVisible();
});


test("真实待办变化后刷新已展开日历，保留月份与日期上下文", async ({ page }) => {
  await login(page, "author");
  await page.goto("/publishing");
  await expect(page.getByRole("button", { name: /^作者待办 \d/ })).toBeVisible();
  await open(page);
  const dueDate = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
  const due = dueDate.slice(0, 7);
  if (due !== new Date().toISOString().slice(0, 7)) await calendar(page).getByRole("button", { name: "下个月" }).click();
  const day = calendar(page).locator(`button[data-date="${dueDate}"]`);
  await day.click();
  await expect(day).toHaveAttribute("aria-pressed", "true");
  const monthButton = calendar(page).getByRole("button", { name: /^本月 \d/ });
  await expect(monthButton).toBeVisible();
  const before = Number((await monthButton.innerText()).match(/[0-9]+/)![0]);
  await page.getByRole("button", { name: "新建投稿", exact: true }).click();
  await expect(calendar(page).getByRole("button", { name: `本月 ${before + 1}`, exact: true })).toBeVisible();
  await expect(calendar(page).getByRole("button", { name: "日历", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(day).toHaveAttribute("aria-pressed", "true");
});
