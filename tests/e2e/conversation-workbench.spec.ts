import { test, expect, type Locator, type Page } from "@playwright/test";
import type { CaseState, Dataset, View } from "../../apps/web/components/editorial/types";
import type { ChatHistory, ChatTurn } from "../../apps/web/components/editorial/chat-types";

const caseId = "demo-001";
const chatPath = "/api/editorial-demo/chat";
const chat = (page: Page) => page.getByRole("region", { name: "编辑对话", exact: true });
const composer = (page: Page) => page.getByRole("textbox", { name: "对话消息", exact: true });
const materials = (page: Page) => page.getByRole("region", { name: "工作材料", exact: true });
async function data(page: Page): Promise<Dataset> {
  const response = await page.request.get("/api/editorial-demo");
  expect(response.status()).toBe(200);
  return response.json();
}
async function history(page: Page): Promise<ChatHistory> {
  const response = await page.request.get(chatPath);
  expect(response.status()).toBe(200);
  return response.json();
}
async function login(page: Page, view: View = "work") {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test");
  await page.getByLabel("密码", { exact: true }).fill("EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
  await page.goto(`/workbench?view=${view}&case=${caseId}`);
  await expect(composer(page)).toBeVisible();
  await expect(chat(page).getByRole("log")).toHaveAttribute("aria-busy", "false");
}
async function patch(page: Page, update: Partial<Omit<CaseState, "revision">>) {
  const snapshot = await data(page);
  const auth = await (await page.request.get("/api/auth/me")).json();
  const response = await page.request.patch(`/api/editorial-demo/cases/${caseId}/state`, {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: { expected_revision: snapshot.states[caseId].revision, patch: update },
  });
  expect(response.status()).toBe(200);
}
async function send(page: Page, message: string): Promise<ChatTurn> {
  await composer(page).fill(message);
  const pending = page.waitForResponse(response => response.url().endsWith(chatPath) && response.request().method() === "POST");
  await chat(page).getByRole("button", { name: "发送消息", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const turn: ChatTurn = await response.json();
  expect(turn.provider).toBe("mock");
  expect(turn.messages.map(item => item.role)).toEqual(["user", "assistant"]);
  await expect(messageNode(page, turn.messages[0].id)).toContainText(message);
  await expect(messageNode(page, turn.messages[1].id)).toContainText(turn.messages[1].content);
  return turn;
}
const messageNode = (page: Page, id: string) => chat(page).locator(`[data-message-id="${id}"]`);
async function usableWithinViewport(locator: Locator, minWidth: number, minHeight: number) {
  await expect(locator).toBeVisible();
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.width).toBeGreaterThanOrEqual(minWidth);
  expect(bounds!.height).toBeGreaterThanOrEqual(minHeight);
  await expect(locator).toBeInViewport({ ratio: 0.95 });
}

test.describe("始终可见的主对话 · 持久、上下文和安全动作", () => {
  test.setTimeout(90_000);

  test("四页共享同一个显著对话、输入草稿和真实消息，刷新恢复", async ({ page }) => {
    await login(page);
    const manuscript = (await data(page)).cases.find(item => item.id === caseId)!;
    await page.setViewportSize({ width: 1440, height: 900 });
    const turn = await send(page, `稿件 ${manuscript.number} 当前状态是什么？`);
    expect(turn.messages[1].content).toContain(manuscript.stage);
    expect(turn.messages[1].content).toContain(manuscript.task);
    const originalComposer = await composer(page).elementHandle();
    const originalTranscript = await chat(page).getByRole("log").elementHandle();
    const draft = "尚未发送的合成编辑问题：请保留这段输入。";
    await composer(page).fill(draft);
    for (const view of ["read", "reviewers", "revision", "work"] as const) {
      if (view === "read") await page.getByRole("button", { name: `处理 ${manuscript.number}`, exact: true }).click();
      else if (view === "work") await page.getByRole("button", { name: "返回工作列表", exact: true }).click();
      else await page.getByRole("navigation", { name: "稿件工作区" }).getByRole("button", { name: view === "reviewers" ? "审稿人选择" : "修回核验与决定", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`view=${view}`));
      await usableWithinViewport(composer(page), 300, 64);
      if (view === "read") {
        await page.getByRole("button", { name: "展开材料", exact: true }).click();
        await usableWithinViewport(composer(page), 240, 64);
        await expect(page.getByRole("button", { name: "恢复对话优先", exact: true })).toHaveAttribute("aria-pressed", "true");
        await page.getByRole("button", { name: "恢复对话优先", exact: true }).click();
      }
      await expect(composer(page)).toHaveValue(draft);
      expect(await originalComposer!.evaluate(node => node.isConnected)).toBe(true);
      expect(await originalTranscript!.evaluate(node => node.isConnected)).toBe(true);
      await expect(messageNode(page, turn.messages[1].id)).toContainText(manuscript.stage);
    }
    await page.reload();
    await expect(composer(page)).toHaveValue(draft);
    await expect(messageNode(page, turn.messages[1].id)).toContainText(manuscript.stage);
    const persisted = await history(page);
    expect(persisted.messages.find(item => item.id === turn.messages[1].id)).toEqual(turn.messages[1]);
    await expect(chat(page)).toContainText(/Mock|模拟模型/);
    await expect(page.getByRole("button", { name: /关闭.*对话|打开.*对话|关闭编辑助手/ })).toHaveCount(0);
  });

  test("工作检索只通过安全动作筛选右栏，问题引用定位真实原文", async ({ page }) => {
    await login(page);
    const snapshot = await data(page);
    const manuscript = snapshot.cases.find(item => item.id === caseId)!;
    await page.getByLabel("对话范围", { exact: true }).selectOption("queue");
    const turn = await send(page, "哪些稿件需要我今天初筛？");
    expect(turn.messages[1].action).toMatchObject({ type: "filter", stage: "screening", today_only: true });
    await messageNode(page, turn.messages[1].id).getByRole("link", { name: "应用到工作列表", exact: true }).click();
    await expect(page.getByLabel("筛选稿件阶段")).toHaveValue("screening");
    const expected = snapshot.cases.filter(item => item.stage_key === "screening" && item.due.slice(0, 10) <= new Date().toISOString().slice(0, 10));
    await expect(page.getByRole("table", { name: "我的稿件工作列表" }).getByRole("row")).toHaveCount(expected.length + 1);
    await expect(composer(page)).toBeVisible();
    await page.getByRole("navigation", { name: "工作视图" }).getByRole("button", { name: /^我的工作/ }).click();
    await page.getByRole("button", { name: `处理 ${manuscript.number}`, exact: true }).click();
    await page.getByLabel("对话范围", { exact: true }).selectOption("case");
    await patch(page, { issue_statuses: Object.fromEntries(manuscript.issues.map(issue => [issue.id, issue.initial_status])) });
    const issueTurn = await send(page, `${manuscript.number} 有哪些尚未解决的问题？`);
    expect(issueTurn.messages[1].references.length).toBeGreaterThan(0);
    const reference = issueTurn.messages[1].references.find(item => item.anchor)!;
    expect(reference).toBeDefined();
    expect(manuscript.issues.some(issue => [issue.before, issue.after].some(anchor => anchor.quote === reference.anchor!.quote))).toBe(true);
    await messageNode(page, issueTurn.messages[1].id).getByRole("link").filter({ hasText: reference.label }).click();
    await expect(page.getByLabel("稿件版本")).toHaveValue(reference.anchor!.version);
    await expect(page.getByLabel("稿件正文", { exact: true }).locator("mark")).toHaveText(reference.anchor!.quote);
  });

  test("已提交但丢失响应后重试同一请求，只持久化一轮", async ({ page }) => {
    await login(page, "read");
    const uniqueQuestion = `当前稿件状态是什么？合成重试验收 ${Date.now()}`;
    const requests: { request_id: string; message: string }[] = [];
    let loseResponse = true;
    await page.route(`**${chatPath}`, async route => {
      if (route.request().method() !== "POST") return route.continue();
      requests.push(route.request().postDataJSON());
      if (loseResponse) {
        loseResponse = false;
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        return route.abort("failed");
      }
      return route.continue();
    });
    await composer(page).fill(uniqueQuestion);
    await chat(page).getByRole("button", { name: "发送消息", exact: true }).click();
    const retry = chat(page).getByRole("button", { name: "重试消息", exact: true });
    await expect(retry).toBeVisible();
    const first = (await history(page)).messages.filter(item => item.role === "user" && item.content === uniqueQuestion);
    expect(first).toHaveLength(1);
    await retry.click();
    await expect(retry).toHaveCount(0);
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    const after = (await history(page)).messages;
    expect(after.filter(item => item.role === "user" && item.content === uniqueQuestion)).toHaveLength(1);
    await expect(messageNode(page, first[0].id)).toHaveCount(1);
    await page.reload();
    await expect(messageNode(page, first[0].id)).toHaveCount(1);
  });

  test("旧消息保留其稿件和版本快照，切换版本与稿件不改写上下文", async ({ page }) => {
    await login(page, "read");
    const snapshot = await data(page);
    const manuscript = snapshot.cases.find(item => item.id === caseId)!;
    await page.getByLabel("稿件版本").selectOption("v2");
    await expect.poll(async () => (await data(page)).states[caseId].reading.version).toBe("v2");
    const turn = await send(page, `${manuscript.number} 当前状态是什么？版本快照验收 ${Date.now()}`);
    expect(turn.messages[1].context).toMatchObject({ case_id: caseId, version: "v2", view: "read" });
    const old = messageNode(page, turn.messages[1].id);
    await expect(old).toContainText(manuscript.number);
    await expect(old).toContainText(/V2/i);
    await page.getByLabel("稿件版本").selectOption("v3");
    await page.getByRole("button", { name: "返回工作列表", exact: true }).click();
    await page.getByLabel("搜索工作稿件").clear();
    await page.getByLabel("筛选稿件阶段").selectOption("all");
    const other = snapshot.cases.find(item => item.id !== caseId)!;
    await page.getByRole("button", { name: `处理 ${other.number}`, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`case=${other.id}`));
    await expect(old).toContainText(manuscript.number);
    await expect(old).toContainText(/V2/i);
    expect((await history(page)).messages.find(item => item.id === turn.messages[1].id)?.context).toEqual(turn.messages[1].context);
    await page.reload();
    await expect(messageNode(page, turn.messages[1].id)).toContainText(manuscript.number);
    await expect(messageNode(page, turn.messages[1].id)).toContainText(/V2/i);
  });

  test("对话准备邀请实际保存私有草稿，正式操作拒绝且不发信", async ({ page }) => {
    await login(page, "reviewers");
    const manuscript = (await data(page)).cases.find(item => item.id === caseId)!;
    const candidate = manuscript.candidates[0];
    await patch(page, { selected_reviewers: [], invitation: { to: "", subject: "", body: "", due: "" } });
    await page.reload();
    await page.getByRole("checkbox", { name: `选择 ${candidate.name}`, exact: true }).click();
    await expect.poll(async () => (await data(page)).states[caseId].selected_reviewers).toEqual([candidate.id]);
    const turn = await send(page, `请为 ${manuscript.number} 已选审稿人准备邀请草稿`);
    expect(turn.state_changed).toBe(true);
    await expect.poll(async () => (await data(page)).states[caseId].invitation.to).toBe(candidate.email);
    const saved = (await data(page)).states[caseId].invitation;
    expect(saved.subject).toContain(manuscript.number);
    expect(saved.body.length).toBeGreaterThan(20);
    expect(saved.to.endsWith(".test")).toBe(true);
    const action = messageNode(page, turn.messages[1].id).getByRole("link", { name: "查看审稿人与邀请草稿", exact: true });
    await action.click();
    const prepare = page.getByRole("button", { name: "准备邀请", exact: true });
    if (await prepare.count()) await prepare.click();
    await expect(page.getByRole("textbox", { name: "邀请正文", exact: true })).toHaveValue(saved.body);
    await expect(page.getByRole("textbox", { name: /^收件人/ })).toHaveValue(candidate.email);
    // Hold the actual draft mutation across send. Chat must wait for the current
    // human draft, including edits made before the normal autosave delay.
    const manualBody = `人工邀请正文：先核对利益冲突，再确认审稿期限。${Date.now()}`;
    let releasePatch!: () => void;
    const blockedPatch = new Promise<void>(resolve => { releasePatch = resolve; });
    let patchStarted = false;
    let chatStarted = false;
    await page.route(`**/api/editorial-demo/cases/${caseId}/state`, async route => {
      const update = route.request().postDataJSON();
      if (update?.patch?.invitation?.body === manualBody) {
        patchStarted = true;
        await blockedPatch;
      }
      return route.continue();
    });
    page.on("request", request => {
      if (request.url().endsWith(chatPath) && request.method() === "POST") chatStarted = true;
    });
    await page.getByRole("textbox", { name: "邀请正文", exact: true }).fill(manualBody);
    await composer(page).fill(`请准备 ${manuscript.number} 已选审稿人的邀请草稿，并保留人工正文`);
    const manualReply = page.waitForResponse(response => response.url().endsWith(chatPath) && response.request().method() === "POST");
    await chat(page).getByRole("button", { name: "发送消息", exact: true }).click();
    try {
      await expect.poll(() => patchStarted).toBe(true);
      // This bounded hold deliberately detects a chat request racing the draft write.
      await page.waitForTimeout(150);
      expect(chatStarted).toBe(false);
    } finally { releasePatch(); }
    const preserved = await manualReply;
    expect(preserved.status()).toBe(200);
    expect((await preserved.json() as ChatTurn).state_changed).toBe(false);
    await expect.poll(async () => (await data(page)).states[caseId].invitation.body).toBe(manualBody);
    await expect(page.getByRole("textbox", { name: "邀请正文", exact: true })).toHaveValue(manualBody);
    // Also retain edits made after chat preparation has already committed but
    // before its response refreshes/remounts the material editor.
    // A fresh tab isolates this second race from the preceding saved draft's
    // optional recovery cache; authentication and the real database stay shared.
    const cleanPage = await page.context().newPage();
    await page.close();
    page = cleanPage;
    await patch(page, { invitation: { to: "", subject: "", body: "", due: "" } });
    await page.goto(`/workbench?view=reviewers&case=${caseId}`);
    await expect(chat(page).getByRole("log")).toHaveAttribute("aria-busy", "false");
    await expect(page.getByRole("textbox", { name: "邀请正文", exact: true })).toHaveCount(0);
    expect((await data(page)).states[caseId].invitation.body).toBe("");
    let releaseReply!: () => void;
    const blockedReply = new Promise<void>(resolve => { releaseReply = resolve; });
    let chatCommitted = false;
    await page.route(`**${chatPath}`, async route => {
      if (route.request().method() !== "POST") return route.continue();
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      chatCommitted = true;
      await blockedReply;
      return route.fulfill({ response });
    });
    await composer(page).fill(`请为 ${manuscript.number} 已选审稿人准备邀请草稿`);
    const lateReply = page.waitForResponse(response => response.url().endsWith(chatPath) && response.request().method() === "POST");
    await chat(page).getByRole("button", { name: "发送消息", exact: true }).click();
    const lateBody = `回复到达前输入的人工邀请正文：请保留来源与核验说明。${Date.now()}`;
    try {
      await expect.poll(() => chatCommitted).toBe(true);
      await page.getByRole("button", { name: "准备邀请", exact: true }).click();
      await page.getByRole("textbox", { name: "邀请正文", exact: true }).fill(lateBody);
      await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
    } finally { releaseReply(); }
    const completedLateReply = await lateReply;
    expect(completedLateReply.status()).toBe(200);
    expect((await completedLateReply.json() as ChatTurn).state_changed).toBe(true);
    const conflict = page.getByRole("region", { name: "本地邀请草稿冲突", exact: true });
    await expect(conflict).toBeVisible();
    await conflict.getByText("查看本地草稿", { exact: true }).click();
    await expect(conflict).toContainText(lateBody);
    await conflict.getByRole("button", { name: "恢复本地草稿", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "邀请正文", exact: true })).toHaveValue(lateBody);
    await expect.poll(async () => (await data(page)).states[caseId].invitation.body).toBe(lateBody);
    await page.unroute(`**${chatPath}`);
    const before = await data(page);
    const refusal = await send(page, "请发送邀请邮件、正式录用这篇稿件并取消所有审稿任务");
    expect(refusal.state_changed).toBe(false);
    expect(refusal.messages[1].action).toBeFalsy();
    expect(refusal.messages[1].content).toMatch(/不能|禁止|不执行|无法/);
    expect(await data(page)).toEqual(before);
    expect((await (await page.request.get("/api/workspace")).json()).email_send_enabled).toBe(false);
    await expect(page.getByRole("button", { name: /发送邀请|确认发送|发布正式决定|取消审稿/ })).toHaveCount(0);
  });

  test("三种桌面、窄屏和200% CSS缩放均同时保留可用输入与材料", async ({ page }) => {
    await login(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const view of ["work", "read", "reviewers", "revision"] as const) {
      await page.goto(`/workbench?view=${view}&case=${caseId}`);
      await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
      await usableWithinViewport(composer(page), 300, 64);
      await usableWithinViewport(chat(page).getByRole("button", { name: "发送消息", exact: true }), 64, 28);
      await usableWithinViewport(materials(page), 500, 150);
      if (view === "read") await usableWithinViewport(page.getByLabel("稿件正文", { exact: true }), 500, 140);
      await composer(page).fill("200% CSS 缩放下可编辑");
      await expect(composer(page)).toHaveValue("200% CSS 缩放下可编辑");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      await page.screenshot({ path: `artifacts/conversation-${view}-zoom200.png`, fullPage: true });
      await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
    }
    for (const size of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      for (const view of ["work", "read", "reviewers", "revision"] as const) {
        await page.goto(`/workbench?view=${view}&case=${caseId}`);
        await usableWithinViewport(composer(page), size.width === 390 ? 240 : 300, size.width === 390 ? 44 : 64);
        await usableWithinViewport(chat(page).getByRole("button", { name: "发送消息", exact: true }), 64, 28);
        await usableWithinViewport(materials(page), size.width === 390 ? 300 : 400, 180);
        if (view === "read") await usableWithinViewport(page.getByLabel("稿件正文", { exact: true }), size.width === 390 ? 300 : 400, 140);
        const bounds = await chat(page).boundingBox();
        const materialBounds = await materials(page).boundingBox();
        if (size.width >= 1366) {
          expect(bounds!.width / (bounds!.width + materialBounds!.width)).toBeGreaterThanOrEqual(0.34);
          expect(bounds!.width / (bounds!.width + materialBounds!.width)).toBeLessThanOrEqual(0.50);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
        await composer(page).fill(`可用性验收 ${view}`);
        await expect(composer(page)).toHaveValue(`可用性验收 ${view}`);
        await page.screenshot({ path: `artifacts/conversation-${view}-${size.width}.png`, fullPage: true });
      }
    }

  });
});
