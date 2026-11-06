import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

const searchEndpoint = /\/api\/search(?:\?|$)/;
const input = (page: Page) => page.getByRole("searchbox", { name: "全局搜索", exact: true });
const results = (page: Page) => page.getByRole("region", { name: "搜索结果", exact: true });
type Session = { csrf_token: string; journal: { name: string } };
type SearchItem = { id: string; title: string; href: string };

async function login(page: Page, role: "editor" | "author" = "editor"): Promise<Session> {
  const health = await page.request.get("/api/health");
  expect(health.status()).toBe(200);
  expect((await health.json()).editorial_model.provider).toBe("mock");
  const response = await page.request.post("/api/auth/login", { data: {
    email: `${role}@publishing.test`,
    password: role === "author" ? "AuthorDemo2026!" : "EditorDemo2026!",
  } });
  expect(response.status()).toBe(200);
  const session = await page.request.get("/api/publishing/session");
  expect(session.status()).toBe(200);
  return session.json();
}

function payload(query: string, items: SearchItem[]) {
  return { query, groups: [{ kind: "conversation", label: "对话", items, has_more: false }] };
}

function conversationItem(title: string): SearchItem {
  const id = randomUUID();
  return { id, title, href: `/?conversation=${id}` };
}

async function createConversation(page: Page, session: Session, title: string): Promise<SearchItem> {
  const response = await page.request.post("/api/conversations", {
    headers: { "X-CSRF-Token": session.csrf_token }, data: { title },
  });
  expect(response.status()).toBe(200);
  const item = await response.json();
  return { id: item.id, title: item.title, href: `/?conversation=${item.id}` };
}

async function createDraft(page: Page, session: Session, title: string): Promise<string> {
  const response = await page.request.post("/api/publishing/drafts", {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { request_id: randomUUID(), title },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).manuscript_id;
}

test("全局搜索在四个工作区位于品牌下方，侧栏移除期刊名与旧对话搜索", async ({ page }) => {
  const session = await login(page);
  for (const path of ["/", "/publishing", "/library", "/workbench"]) {
    await page.goto(path);
    const search = input(page);
    await expect(search).toHaveCount(1);
    await expect(search).toBeVisible();
    const sidebar = search.locator("xpath=ancestor::aside[1]");
    await expect(sidebar.getByText(session.journal.name, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("searchbox", { name: "搜索对话", exact: true })).toHaveCount(0);
    const brandBox = await sidebar.getByText("Pivot", { exact: true }).first().boundingBox();
    const searchBox = await search.boundingBox();
    expect(brandBox).not.toBeNull(); expect(searchBox).not.toBeNull();
    expect(searchBox!.y).toBeGreaterThanOrEqual(brandBox!.y + brandBox!.height);
  }
});

test("真实全局搜索按本人对话、内部资料与旧稿件定位并打开授权目标", async ({ page }) => {
  const session = await login(page);
  const marker = randomUUID().slice(0, 8);
  const conversation = await createConversation(page, session, `完全合成全局对话 ${marker}`);
  const dossierTitle = `完全合成全局资料 ${marker}`;
  const created = await page.request.post("/api/dossiers", {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { request_id: randomUUID(), title: dossierTitle, source_kind: "synthetic", source_note: "全部为全局搜索自动验收原创合成资料。", authorized_material: true },
  });
  expect(created.status()).toBe(200);
  const dossierId = (await created.json()).dossier_id as string;
  // The health guard above fixes this existing legacy command to its Mock provider.
  const legacyResponse = await page.request.post("/api/conversations/commands", {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { request_id: randomUUID(), conversation_id: conversation.id, message: "创建一篇测试稿件，并交给编辑初筛。" },
  });
  expect(legacyResponse.status()).toBe(200);
  const legacy = (await legacyResponse.json()).manuscript as { id: string; title: string };

  await page.goto("/");
  await input(page).fill(marker);
  await expect(results(page).getByRole("link", { name: conversation.title, exact: true })).toBeVisible();
  await expect(results(page).getByRole("link", { name: dossierTitle, exact: true })).toBeVisible();
  await page.screenshot({ path: `artifacts/search/${test.info().project.name}-desktop-results.png`, fullPage: true });
  await input(page).fill(conversation.title);
  await expect(results(page).getByRole("heading", { name: "对话", exact: true })).toBeVisible();
  await results(page).getByRole("link", { name: conversation.title, exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("conversation")).toBe(conversation.id);
  await expect(page.locator(`[data-conversation-id="${conversation.id}"]`)).toHaveAttribute("aria-current", "true");

  await input(page).fill(dossierTitle);
  await expect(results(page).getByRole("heading", { name: "内部资料", exact: true })).toBeVisible();
  await results(page).getByRole("link", { name: dossierTitle, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/library\\?dossier=${dossierId}$`));
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue(dossierTitle);

  await input(page).fill(legacy.id.slice(0, 8));
  const legacyLink = results(page).getByRole("link", { name: legacy.title, exact: true });
  await expect(legacyLink).toHaveAttribute("href", `/?manuscript=${legacy.id}`);
  await legacyLink.click();
  await expect.poll(() => new URL(page.url()).searchParams.get("manuscript")).toBe(legacy.id);
  await expect(page.getByTestId("manuscript-detail")).toContainText(legacy.title);
});

test("真实作者可以按稿件编号搜索并打开本人正式草稿", async ({ page }) => {
  const session = await login(page, "author");
  const title = `完全合成全局正式稿 ${randomUUID().slice(0, 8)}`;
  const id = await createDraft(page, session, title);
  const detailResponse = await page.request.get(`/api/publishing/manuscripts/${id}`);
  expect(detailResponse.status()).toBe(200);
  const detail = await detailResponse.json();
  expect(detail.number).toEqual(expect.any(String));
  await page.goto("/publishing");
  await input(page).fill(detail.number);
  const link = results(page).getByRole("link", { name: title, exact: true });
  await expect(link).toHaveAttribute("href", `/publishing?manuscript=${id}`);
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/publishing\\?manuscript=${id}$`));
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(title);
});

test("UI fixture：新搜索立即清除旧结果，迟到响应不能覆盖当前关键词", async ({ page }) => {
  await login(page);
  let started!: () => void, release!: () => void, finished!: () => void;
  const requested = new Promise<void>(resolve => { started = resolve; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  const settled = new Promise<void>(resolve => { finished = resolve; });
  const oldItem = conversationItem("合成旧关键词结果");
  const currentItem = conversationItem("合成新关键词结果");
  await page.route(searchEndpoint, async route => {
    const query = new URL(route.request().url()).searchParams.get("q")!;
    if (query === "旧关键词") {
      started(); await gate;
      try { await route.fulfill({ json: payload(query, [oldItem]) }); } catch { /* The obsolete fetch may already be aborted. */ }
      finally { finished(); }
    } else await route.fulfill({ json: payload(query, [query === "已加载" ? oldItem : currentItem]) });
  });
  await page.goto("/");
  try {
    await input(page).fill("已加载");
    await expect(results(page).getByRole("link", { name: oldItem.title, exact: true })).toBeVisible();
    await input(page).fill("旧关键词"); await requested;
    await expect(results(page).getByRole("link", { name: oldItem.title })).toHaveCount(0);
    await input(page).fill("新关键词");
    await expect(results(page).getByRole("link", { name: oldItem.title })).toHaveCount(0);
    await expect(results(page).getByRole("link", { name: currentItem.title, exact: true })).toBeVisible();
    release(); await settled;
    await expect(results(page).getByRole("link", { name: oldItem.title })).toHaveCount(0);
    await expect(results(page).getByRole("link", { name: currentItem.title, exact: true })).toBeVisible();
    await expect(input(page)).toHaveValue("新关键词");
  } finally { release(); }
});

test("UI fixture：服务端返回不安全地址时整批结果关闭，显式重试才恢复", async ({ page }) => {
  await login(page);
  const safe = conversationItem("合成安全搜索目标");
  let calls = 0;
  await page.route(searchEndpoint, route => {
    calls += 1;
    const query = new URL(route.request().url()).searchParams.get("q")!;
    return route.fulfill({ json: payload(query, calls === 1
      ? [safe, { id: randomUUID(), title: "不应出现的合成外部目标", href: "https://example.test/collect" }]
      : [safe]) });
  });
  await page.goto("/");
  await input(page).fill("合成目标");
  await expect(results(page).getByRole("alert")).toHaveText("搜索暂时不可用，请重试。");
  await expect(results(page).getByRole("link")).toHaveCount(0);
  await expect(page.locator('a[href="https://example.test/collect"]')).toHaveCount(0);
  expect(calls).toBe(1);
  await results(page).getByRole("button", { name: "重新搜索", exact: true }).click();
  await expect(results(page).getByRole("link", { name: safe.title, exact: true })).toHaveAttribute("href", safe.href);
  expect(calls).toBe(2);
});

for (const status of [401, 403]) {
  test(`UI fixture：搜索返回 ${status} 后清除旧结果并要求重新打开工作区`, async ({ page }) => {
    await login(page);
    const item = conversationItem("合成已撤权搜索结果");
    await page.route(searchEndpoint, route => {
      const query = new URL(route.request().url()).searchParams.get("q")!;
      return query === "可见" ? route.fulfill({ json: payload(query, [item]) }) : route.fulfill({ status, json: { detail: "synthetic_session_changed" } });
    });
    await page.goto("/");
    await input(page).fill("可见");
    await expect(results(page).getByRole("link", { name: item.title, exact: true })).toBeVisible();
    await input(page).fill("已撤权");
    await expect(results(page).getByRole("alert")).toHaveText("登录或身份已变化，请重新打开工作区。");
    await expect(results(page).getByRole("link")).toHaveCount(0);
    await expect(results(page).getByRole("button", { name: "重新搜索", exact: true })).toHaveCount(0);
  });
}

test("UI fixture：搜索支持箭头导航与 Escape，输入法确认 Enter 不打开结果", async ({ page }) => {
  const session = await login(page);
  const first = await createConversation(page, session, `合成键盘目标甲 ${randomUUID().slice(0, 8)}`);
  const last = await createConversation(page, session, `合成键盘目标乙 ${randomUUID().slice(0, 8)}`);
  await page.route(searchEndpoint, route => route.fulfill({ json: payload(new URL(route.request().url()).searchParams.get("q")!, [first, last]) }));
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "工作空间", exact: true })).toBeVisible();
  const initialURL = page.url();
  const search = input(page);
  await search.fill("合成键盘");
  const firstLink = results(page).getByRole("link", { name: first.title, exact: true });
  const lastLink = results(page).getByRole("link", { name: last.title, exact: true });
  await expect(firstLink).toBeVisible();
  await search.dispatchEvent("compositionstart");
  await search.dispatchEvent("keydown", { key: "Enter", code: "Enter", keyCode: 229, which: 229, isComposing: true, bubbles: true, cancelable: true });
  await search.dispatchEvent("compositionend");
  await expect(page).toHaveURL(initialURL);
  await expect(firstLink).toBeVisible();
  await search.press("ArrowDown"); await expect(firstLink).toBeFocused();
  await page.keyboard.press("ArrowDown"); await expect(lastLink).toBeFocused();
  await page.keyboard.press("Home"); await expect(firstLink).toBeFocused();
  await page.keyboard.press("End"); await expect(lastLink).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(results(page)).toHaveCount(0);
  await expect(search).toBeFocused();
  await search.fill("合成键盘再查");
  await expect(firstLink).toBeVisible();
  await search.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect.poll(() => new URL(page.url()).searchParams.get("conversation")).toBe(first.id);
  await expect(page.locator(`[data-conversation-id="${first.id}"]`)).toHaveAttribute("aria-current", "true");
});

test("390px 搜索结果留在导航抽屉内，Escape 只关闭搜索且页面不横溢出", async ({ page }) => {
  await login(page);
  const item = conversationItem("完全合成的移动搜索长题名，用于核对换行与结果点击范围，不包含保密资料");
  await page.route(searchEndpoint, route => route.fulfill({ json: payload(new URL(route.request().url()).searchParams.get("q")!, [item]) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "侧栏", exact: true });
  await expect(drawer).toBeVisible();
  await input(page).fill("移动搜索");
  await expect(drawer.getByRole("region", { name: "搜索结果", exact: true })).toBeVisible();
  const link = results(page).getByRole("link", { name: item.title, exact: true });
  await expect(link).toBeInViewport();
  expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `artifacts/search/${test.info().project.name}-390-results.png`, fullPage: true });
  await input(page).press("ArrowDown");
  await page.keyboard.press("Escape");
  await expect(results(page)).toHaveCount(0);
  await expect(drawer).toBeVisible();
  await expect(input(page)).toBeFocused();
  await page.setViewportSize({ width: 1280, height: 800 });
  await input(page).fill("移动搜索再次查看");
  await expect(results(page)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(input(page)).toBeHidden();
  await expect(results(page)).toHaveCount(0);
});

test("UI fixture：重新聚焦相同关键词重新核对权限，等待期间不恢复旧结果", async ({ page }) => {
  await login(page);
  const item = conversationItem("重新核对前的合成私人标题");
  let calls = 0; let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(searchEndpoint, async route => {
    calls += 1;
    const query = new URL(route.request().url()).searchParams.get("q")!;
    if (calls === 1) return route.fulfill({ json: payload(query, [item]) });
    await gate; return route.fulfill({ json: payload(query, []) });
  });
  try {
    await page.goto("/");
    await input(page).fill("重新核对");
    await expect(results(page).getByRole("link", { name: item.title, exact: true })).toBeVisible();
    await input(page).press("Escape");
    await page.getByRole("heading", { level: 1 }).click();
    await input(page).focus();
    await expect.poll(() => calls).toBe(2);
    await expect(results(page).getByRole("link")).toHaveCount(0);
    await expect(results(page).getByText("正在搜索…", { exact: true })).toBeVisible();
    release();
    await expect(results(page).getByText("没有找到相关结果。", { exact: true })).toBeVisible();
    expect(calls).toBe(2);
  } finally { release(); }
});

test("搜索不清除作者未保存资料，选择结果取消离开后保留原表单与结果", async ({ page }) => {
  const session = await login(page, "author");
  const firstTitle = `合成搜索离开保护甲 ${randomUUID().slice(0, 8)}`;
  const nextTitle = `合成搜索离开保护乙 ${randomUUID().slice(0, 8)}`;
  const firstId = await createDraft(page, session, firstTitle);
  const nextId = await createDraft(page, session, nextTitle);
  await page.goto(`/publishing?manuscript=${firstId}`);
  const title = page.getByLabel("标题", { exact: true });
  const draft = "仅在浏览器内的完全合成未保存题名";
  await title.fill(draft);
  const initialURL = page.url();
  await input(page).fill(nextTitle);
  const target = results(page).getByRole("link", { name: nextTitle, exact: true });
  await expect(target).toHaveAttribute("href", `/publishing?manuscript=${nextId}`);
  await expect(title).toHaveValue(draft);
  await expect(page).toHaveURL(initialURL);
  const leaving = page.waitForEvent("dialog");
  const click = target.click({ noWaitAfter: true });
  const prompt = await leaving;
  expect(["confirm", "beforeunload"]).toContain(prompt.type());
  await prompt.dismiss(); await click;
  await expect(page).toHaveURL(initialURL);
  await expect(title).toHaveValue(draft);
  await expect(target).toBeVisible();
  const persisted = await page.request.get(`/api/publishing/manuscripts/${firstId}`);
  expect(persisted.status()).toBe(200);
  expect((await persisted.json()).version.data.title).toBe(firstTitle);
});
