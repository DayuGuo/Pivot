import { test, expect, type Page } from "@playwright/test";
import type { Case, CaseState, Dataset } from "../../apps/web/components/editorial/types";

// Only the editor's private state for the synthetic demo-001 is changed. Each
// test reads the current revision before resetting it, so repeated runs are safe.
const caseId = "demo-001";
const statePath = `/api/editorial-demo/cases/${caseId}/state`;
const passwords = { editor: "EditorDemo2026!", author: "AuthorDemo2026!", reviewer: "ReviewerDemo2026!" };
async function login(page: Page, role: keyof typeof passwords = "editor") {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}@publishing.test`);
  await page.getByLabel("密码", { exact: true }).fill(passwords[role]);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page.getByRole("navigation", { name: "工作空间" })).toBeVisible();
}
async function dataset(page: Page): Promise<Dataset> {
  const response = await page.request.get("/api/editorial-demo");
  expect(response.status()).toBe(200);
  return response.json();
}
async function state(page: Page) { return (await dataset(page)).states[caseId]; }
async function reset(page: Page): Promise<Case> {
  const data = await dataset(page);
  const manuscript = data.cases.find(c => c.id === caseId)!;
  const version = manuscript.versions.at(-1)!;
  const auth = await (await page.request.get("/api/auth/me")).json();
  const response = await page.request.patch(statePath, {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: { expected_revision: data.states[caseId].revision, patch: {
      selected_reviewers: [], issue_statuses: Object.fromEntries(manuscript.issues.map(i => [i.id, i.initial_status])),
      notes: "", version_notes: {}, invitation: { to: "", subject: "", body: "", due: "" },
      decision: { outcome: "", body: "" }, reading: { version: version.id, section: version.sections[0].id }, ai_results: [],
    } },
  });
  expect(response.status()).toBe(200);
  return manuscript;
}
async function open(page: Page, view = "work") {
  await page.goto(`/workbench?view=${view}&case=${caseId}`);
  await expect(page.getByRole("navigation", { name: "工作视图" })).toBeVisible();
}
async function openProgressPreview(page: Page) {
  const details = page.locator("details").filter({ has: page.getByText("稿件进度", { exact: true }) });
  if (!(await details.evaluate(node => (node as HTMLDetailsElement).open))) await details.locator("summary").click();
}
async function readingTools(page: Page) {
  for (const name of ["目录", "问题与笔记"]) {
    const control = page.getByRole("button", { name, exact: true });
    if (await control.getAttribute("aria-expanded") === "false") await control.click();
  }
}
async function persisted<T>(page: Page, read: (value: CaseState) => T, expected: T) {
  await expect.poll(async () => read(await state(page))).toEqual(expected);
}
async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

test.describe("合成编辑工作台 · 跨浏览器验收", () => {
  test.setTimeout(60_000);

  test("已有编辑入口贯穿四页，队列筛选、常用视图与滚动位置恢复", async ({ page }) => {
    await login(page);
    const manuscript = await reset(page);
    const before = await dataset(page);
    const ownView = "浏览器验收 · 当前稿件";
    await page.getByRole("navigation", { name: "工作空间" }).getByRole("button", { name: /我的工作/ }).click();
    await expect(page).toHaveURL(/\/workbench/);
    await expect(page.getByText("合成数据演示", { exact: true })).toBeVisible();
    const table = page.getByRole("table", { name: "我的稿件工作列表" });
    await expect(table.getByRole("row")).toHaveCount(before.cases.length + 1);
    await page.getByLabel("对话范围", { exact: true }).selectOption("queue");
    await page.getByRole("textbox", { name: "对话消息", exact: true }).fill("哪些稿件需要我今天初筛？");
    const filtered = page.waitForResponse(response => response.url().endsWith("/api/editorial-demo/chat") && response.request().method() === "POST");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    expect((await filtered).status()).toBe(200);
    await expect(page.getByLabel("筛选稿件阶段")).toHaveValue("screening");
    await expect(page.getByRole("log")).toContainText(/初筛/);
    await page.getByRole("navigation", { name: "工作视图" }).getByRole("button", { name: /^我的工作/ }).click();
    await page.getByLabel("搜索工作稿件").fill("不存在的合成编号");
    await expect(page.getByRole("heading", { name: "没有符合条件的工作" })).toBeVisible();
    await page.getByRole("button", { name: "重置筛选" }).click();
    await page.getByLabel("搜索工作稿件").fill(manuscript.number);
    await page.getByLabel("筛选稿件阶段").selectOption(manuscript.stage_key);
    await page.getByLabel("工作排序").selectOption("title");
    await page.getByText("保存视图", { exact: true }).click();
    await page.getByLabel("视图名称").fill(ownView);
    await page.locator("details").getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByRole("navigation", { name: "工作视图" }).getByRole("button", { name: ownView })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("搜索工作稿件")).toHaveValue(manuscript.number);
    await expect(page.getByLabel("工作排序")).toHaveValue("title");
    await expect(table.getByRole("row")).toHaveCount(2);
    await page.getByRole("button", { name: `处理 ${manuscript.number}` }).click();
    const tabs = page.getByRole("navigation", { name: "稿件工作区" });
    await expect(page.getByLabel("稿件正文", { exact: true })).toBeVisible();
    await tabs.getByRole("button", { name: "审稿人选择", exact: true }).click();
    await expect(page.getByRole("heading", { name: "选择审稿人", exact: true })).toBeVisible();
    await tabs.getByRole("button", { name: "修回核验与决定" }).click();
    await expect(page.getByRole("heading", { name: "修回核验", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "返回工作列表" }).click();
    await expect(page.getByLabel("搜索工作稿件")).toHaveValue(manuscript.number);
    await page.getByLabel("搜索工作稿件").clear();
    await page.getByLabel("筛选稿件阶段").selectOption("all");
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.screenshot({ path: "artifacts/workbench-work-1366.png", fullPage: true });
    const queue = table.locator("..");
    const offset = await queue.evaluate(node => { node.scrollTop = node.scrollHeight; return node.scrollTop; });
    expect(offset).toBeGreaterThan(0);
    await openProgressPreview(page);
    await page.getByRole("button", { name: "打开稿件", exact: true }).click();
    await page.getByRole("button", { name: "返回工作列表" }).click();
    await expect.poll(() => queue.evaluate(node => node.scrollTop)).toBeCloseTo(offset, 0);
    await page.getByRole("navigation", { name: "工作视图" }).getByRole("button", { name: ownView }).click();
    await expect(page.getByLabel("搜索工作稿件")).toHaveValue(manuscript.number);
    await expect(page.getByLabel("筛选稿件阶段")).toHaveValue(manuscript.stage_key);
    // Remove only this test's named view, preserving all unrelated user views.
    const auth = await (await page.request.get("/api/auth/me")).json();
    const views = (await dataset(page)).saved_views.filter(v => v.name !== ownView);
    expect((await page.request.put("/api/editorial-demo/views", { headers: { "X-CSRF-Token": auth.csrf_token }, data: { views } })).status()).toBe(200);
  });

  test("原文证据精确定位版本与文件，笔记失败重试、阅读位置与阅读设置恢复", async ({ page }) => {
    await login(page);
    const manuscript = await reset(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, "read");
    await readingTools(page);
    const issue = manuscript.issues.find(i => i.id === "issue-3")!;
    const evidence = page.getByRole("complementary", { name: "问题与编辑笔记" });
    await evidence.getByRole("button", { name: `${issue.before.version} · ${issue.before.location}`, exact: true }).click();
    await expect(page.getByLabel("稿件版本")).toHaveValue(issue.before.version);
    await expect(page.getByLabel("稿件正文", { exact: true }).locator("mark")).toHaveText(issue.before.quote);
    await expect(page.getByText(`定位原文：${issue.before.location}`, { exact: false })).toBeVisible();
    const original = page.getByRole("link", { name: "查看对应版本原稿", exact: true });
    await expect(original).toHaveAttribute("href", new RegExp(`${issue.before.file}$`));
    const file = await page.request.get((await original.getAttribute("href"))!);
    expect(file.status()).toBe(200);
    expect(file.headers()["content-disposition"]).toContain("attachment");
    expect(await file.text()).toContain(issue.before.quote);
    await page.getByLabel("正文字号").selectOption("18");
    await expect(page.getByLabel("稿件正文", { exact: true }).locator("article")).toHaveCSS("font-size", "18px");
    const separator = page.getByRole("separator", { name: "调整问题面板宽度" });
    await separator.focus();
    await page.keyboard.press("End");
    await expect(separator).toHaveAttribute("aria-valuenow", "480");
    await page.keyboard.press("Home");
    await page.keyboard.press("ArrowLeft");
    await expect(separator).toHaveAttribute("aria-valuenow", "280");
    await page.getByRole("button", { name: "专注阅读", exact: true }).click();
    await expect(evidence).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "稿件章节" })).toHaveCount(0);
    await page.getByRole("button", { name: "退出专注" }).click();
    await page.getByRole("tab", { name: "编辑笔记", exact: true }).click();
    let fail = true;
    await page.route(`**${statePath}`, route => {
      const body = route.request().postDataJSON();
      if (fail && body?.patch?.version_notes) return route.abort("failed");
      return route.continue();
    });
    const note = "合成验收笔记：先核对站点重采样单位，再确认区间算法。";
    await page.getByLabel("版本笔记", { exact: true }).fill(note);
    await page.getByRole("button", { name: "保存笔记", exact: true }).click();
    await expect(page.getByText("保存失败，未保存笔记已保留，可重试。", { exact: false })).toBeVisible();
    await expect(page.getByLabel("版本笔记", { exact: true })).toHaveValue(note);
    await page.getByRole("navigation", { name: "稿件工作区" }).getByRole("button", { name: "审稿人选择", exact: true }).click();
    const candidate = manuscript.candidates[0];
    await page.getByRole("checkbox", { name: `选择 ${candidate.name}`, exact: true }).click();
    await persisted(page, value => value.selected_reviewers, [candidate.id]);
    await page.getByRole("navigation", { name: "稿件工作区" }).getByRole("button", { name: "稿件阅读", exact: true }).click();
    await expect(page.getByText("已恢复未保存的版本笔记，正在重新保存。", { exact: false })).toBeVisible();
    await page.getByRole("tab", { name: "编辑笔记", exact: true }).click();
    await expect(page.getByLabel("版本笔记", { exact: true })).toHaveValue(note);
    await expect(page.getByText("保存失败，未保存笔记已保留，可重试。", { exact: false })).toBeVisible();
    fail = false;
    await page.getByRole("button", { name: "重试保存", exact: true }).click();
    await persisted(page, value => value.version_notes.v2, note);
    await page.getByRole("navigation", { name: "稿件章节" }).getByRole("button", { name: /5 讨论/ }).click();
    await persisted(page, value => value.reading, { version: "v2", section: "discussion", paragraph: 0 });
    const reader = page.getByLabel("稿件正文", { exact: true });
    const resumedParagraph = reader.locator("#article-discussion > p").nth(2);
    const scrollDelta = await resumedParagraph.evaluate(node => {
      const viewport = node.closest('[aria-label="稿件正文"]')!;
      return node.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 24;
    });
    await reader.hover();
    await page.mouse.wheel(0, scrollDelta);
    await persisted(page, value => value.reading, { version: "v2", section: "discussion", paragraph: 2 });
    await page.reload();
    await expect(page.getByLabel("稿件版本")).toHaveValue("v2");
    await expect(page.getByLabel("正文字号")).toHaveValue("18");
    await expect(separator).toHaveAttribute("aria-valuenow", "280");
    await expect(page.getByRole("navigation", { name: "稿件章节" }).getByRole("button", { name: /5 讨论/ })).toHaveAttribute("aria-current", "location");
    await expect(resumedParagraph).toHaveText(manuscript.versions.find(version => version.id === "v2")!.sections.find(section => section.id === "discussion")!.paragraphs[2]);
    // A long paragraph can exceed the companion reader height; its restored start
    // must be visible, and the precise top offset below verifies the location.
    await expect(resumedParagraph).toBeInViewport();
    const restoredOffset = await resumedParagraph.evaluate(node => node.getBoundingClientRect().top - node.closest('[aria-label="稿件正文"]')!.getBoundingClientRect().top);
    expect(restoredOffset).toBeGreaterThanOrEqual(0);
    expect(restoredOffset).toBeLessThan(80);
    await page.getByRole("tab", { name: "编辑笔记", exact: true }).click();
    await expect(page.getByLabel("版本笔记", { exact: true })).toHaveValue(note);
    await page.screenshot({ path: "artifacts/workbench-reader-1440.png", fullPage: true });
    await page.getByLabel("稿件版本").selectOption("v3");
    await expect(page.getByLabel("版本笔记", { exact: true })).toHaveValue("");
  });

  test("候选筛选与连续预览恢复，比较与邀请完整内容持久化且不发送", async ({ page }) => {
    await login(page);
    const manuscript = await reset(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await open(page, "reviewers");
    const [first, second] = manuscript.candidates;
    await page.getByLabel("搜索候选人", { exact: true }).fill("无此合成候选");
    await expect(page.getByRole("heading", { name: "没有符合条件的候选人" })).toBeVisible();
    await page.getByRole("button", { name: "清除筛选" }).click();
    await page.getByRole("combobox", { name: "研究方向", exact: true }).selectOption(first.topics[0]);
    await expect(page.getByRole("checkbox", { name: `选择 ${first.name}`, exact: true })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: `选择 ${second.name}`, exact: true })).toHaveCount(0);
    await page.getByRole("combobox", { name: "研究方向", exact: true }).selectOption("");
    const preview = page.getByRole("complementary", { name: "候选人预览" });
    await preview.getByRole("button", { name: "下一位" }).click();
    await expect(preview.getByRole("heading", { name: second.name, exact: true })).toBeVisible();
    await expect(preview).toContainText(second.sources[0]);
    await expect(preview).toContainText("尚未经外部核实");
    await page.getByRole("checkbox", { name: `选择 ${first.name}`, exact: true }).click();
    await persisted(page, value => value.selected_reviewers, [first.id]);
    await page.getByRole("checkbox", { name: `选择 ${second.name}`, exact: true }).click();
    await persisted(page, value => value.selected_reviewers, [first.id, second.id]);
    await page.getByRole("button", { name: "比较已选（2）", exact: true }).click();
    const comparison = page.getByRole("region", { name: "已选候选人比较" });
    await expect(comparison).toContainText(first.name);
    await expect(comparison).toContainText(second.name);
    await page.getByLabel("搜索候选人", { exact: true }).fill(second.name);
    await page.reload();
    await expect(page.getByLabel("搜索候选人", { exact: true })).toHaveValue(second.name);
    await expect(preview.getByRole("heading", { name: second.name, exact: true })).toBeVisible();
    await page.getByLabel("搜索候选人", { exact: true }).clear();
    await expect(page.getByRole("checkbox", { name: `选择 ${first.name}`, exact: true })).toBeChecked();
    await page.getByRole("button", { name: "准备邀请", exact: true }).click();
    await expect(page.getByRole("textbox", { name: /^收件人/ })).toHaveValue(`${first.email}, ${second.email}`);
    expect([first.email, second.email].every(email => email.endsWith(".test"))).toBe(true);
    const body = "尊敬的合成审稿人：\n请核验本合成稿件的不确定性与可重复研究材料。\n本信仅为演示草稿。";
    await page.getByRole("textbox", { name: "邀请正文", exact: true }).fill(body);
    await page.getByLabel("审稿期限", { exact: true }).fill("2026-12-08");
    await page.getByRole("button", { name: "保存并查看完整预览", exact: true }).click();
    const snapshot = page.getByRole("region", { name: "邀请草稿完整预览" });
    await expect(snapshot).toBeFocused();
    await expect(snapshot).toContainText(body);
    await expect(snapshot).toContainText("2026-12-08");
    await expect(snapshot).toContainText(first.email);
    await expect(snapshot).toContainText("演示模式禁止发送邮件或发布正式决定");
    await snapshot.getByText("核对快照依据").click();
    await expect(snapshot).toContainText(/SHA-256：[a-f0-9]{64}/);
    await persisted(page, value => value.invitation.body, body);
    await page.screenshot({ path: "artifacts/workbench-invitation-1920.png", fullPage: true });
    await page.reload();
    await page.getByRole("button", { name: "准备邀请", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "邀请正文", exact: true })).toHaveValue(body);
    await expect(page.getByLabel("审稿期限", { exact: true })).toHaveValue("2026-12-08");
    expect((await (await page.request.get("/api/workspace")).json()).email_send_enabled).toBe(false);
    await expect(page.getByRole("button", { name: /发送邀请|确认发送/ })).toHaveCount(0);
  });

  test("两轮修回核验关联差异，决定初始中性、草稿恢复且保留进行中任务", async ({ page }) => {
    await login(page);
    const manuscript = await reset(page);
    const originalRounds = structuredClone(manuscript.rounds);
    await open(page, "revision");
    await expect(page.getByRole("combobox", { name: "审稿轮次", exact: true })).toHaveValue("2");
    await page.getByRole("combobox", { name: "审稿轮次", exact: true }).selectOption("1");
    const firstIssue = manuscript.issues.find(i => i.id === "issue-2")!;
    await expect(page.getByRole("heading", { name: firstIssue.title, exact: true })).toBeVisible();
    await page.getByLabel(`${firstIssue.title}核验状态`, { exact: true }).selectOption("resolved");
    await persisted(page, value => value.issue_statuses[firstIssue.id], "resolved");
    await page.getByRole("combobox", { name: "审稿轮次", exact: true }).selectOption("2");
    const secondIssue = manuscript.issues.find(i => i.id === "issue-3")!;
    const issue = page.getByRole("article").filter({ has: page.getByRole("heading", { name: secondIssue.title, exact: true }) });
    await expect(issue).toContainText(secondIssue.before.quote);
    await expect(issue).toContainText(secondIssue.after.quote);
    await issue.getByRole("button", { name: "定位修改", exact: true }).click();
    await expect(page.getByLabel("稿件正文", { exact: true }).locator("mark")).toHaveText(secondIssue.after.quote);
    await page.getByRole("navigation", { name: "稿件工作区" }).getByRole("button", { name: "修回核验与决定" }).click();
    await page.getByLabel(`${secondIssue.title}核验状态`, { exact: true }).selectOption("resolved");
    await persisted(page, value => value.issue_statuses[secondIssue.id], "resolved");
    await page.getByRole("button", { name: "准备编辑决定", exact: true }).click();
    const decision = page.getByRole("region", { name: "编辑决定准备" });
    await expect(page.getByRole("combobox", { name: "拟定结果", exact: true })).toHaveValue("");
    await expect(page.getByRole("textbox", { name: "决定信正文", exact: true })).toHaveValue("");
    await expect(decision.getByRole("heading", { name: /仍在进行的审稿任务（1）/ })).toBeVisible();
    await expect(decision).toContainText("合成审稿人3");
    await expect(decision).toContainText("等待回复 · 期限 2026-11-06");
    await expect(decision).toContainText("准备决定不会取消审稿任务");
    await page.getByRole("button", { name: "保存并查看决定信预览" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "请选择拟定结果" })).toBeVisible();
    await page.getByRole("combobox", { name: "拟定结果", exact: true }).selectOption("major_revision");
    const letter = "各位合成作者：\n请补充数据字典并逐条回复未完成事项。\n这是内部准备的演示决定草稿，尚未发布。";
    await page.getByRole("textbox", { name: "决定信正文", exact: true }).fill(letter);
    await page.getByLabel("内部编辑笔记", { exact: true }).fill("仅编辑部：仍须等候约定期限内的审稿任务。");
    await page.getByRole("button", { name: "保存并查看决定信预览" }).click();
    const snapshot = page.getByRole("region", { name: "决定信草稿完整预览" });
    await expect(snapshot).toBeFocused();
    await expect(snapshot).toContainText(letter);
    await expect(snapshot).toContainText("大修");
    await persisted(page, value => value.decision, { outcome: "major_revision", body: letter });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.screenshot({ path: "artifacts/workbench-decision-1920.png", fullPage: true });
    await page.reload();
    await page.getByRole("button", { name: "准备编辑决定", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "决定信正文", exact: true })).toHaveValue(letter);
    await expect(page.getByRole("combobox", { name: "拟定结果", exact: true })).toHaveValue("major_revision");
    await expect(page.getByLabel(`${secondIssue.title}核验状态`, { exact: true })).toHaveValue("resolved");
    expect((await dataset(page)).cases.find(c => c.id === caseId)!.rounds).toEqual(originalRounds);
    await expect(page.getByRole("button", { name: /取消审稿|发布正式决定|发送决定/ })).toHaveCount(0);
  });

  test("AI 演示任务可取消、失败后重试，改写与人工处理保留版本依据", async ({ page }) => {
    await login(page);
    const manuscript = await reset(page);
    await open(page, "read");
    await page.getByText("模拟检查工具", { exact: true }).click();
    const assistant = page.getByRole("region", { name: "模拟检查工具", exact: true });
    await expect(assistant).toContainText("模拟模型 · 不执行正式操作");
    await expect(assistant).toContainText(`${manuscript.number} / V3 / 第2轮`);
    const initial = await state(page);
    await assistant.getByRole("button", { name: "分析当前版本", exact: true }).click();
    await expect(assistant.getByRole("progressbar")).toBeVisible();
    await assistant.getByRole("button", { name: "取消任务", exact: true }).click();
    await expect(assistant).toContainText("已取消，未继续生成结果");
    // Wait beyond the entire simulated job to detect a late write after cancel.
    await page.waitForTimeout(2300);
    expect((await state(page)).ai_results).toEqual([]);
    expect((await state(page)).revision).toBe(initial.revision);
    let failAnalysis = true;
    await page.route(`**${statePath}`, route => {
      const body = route.request().postDataJSON();
      if (failAnalysis && body?.patch?.ai_results?.length) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "合成验收：分析结果保存失败" }) });
      return route.continue();
    });
    await assistant.getByRole("button", { name: "重新分析", exact: true }).click();
    await expect(assistant).toContainText("保存失败，可重试");
    expect((await state(page)).ai_results).toEqual([]);
    failAnalysis = false;
    await assistant.getByRole("button", { name: "重试模拟检查", exact: true }).click();
    await expect(assistant).toContainText("模拟分析已保存");
    const [first, second] = manuscript.issues.filter(issue => [issue.before.version, issue.after.version].includes(initial.reading.version));
    const rewritten = "人工改写的演示线索：对照缺失比例与完整案例分析，仍待核实。";
    await assistant.getByLabel(`改写AI建议 ${first.title}`, { exact: true }).fill(rewritten);
    await assistant.getByLabel(`改写AI建议 ${first.title}`, { exact: true }).press("Tab");
    await persisted(page, value => value.ai_results.find(r => r.issue_id === first.id)?.text, rewritten);
    await assistant.getByLabel(`处理AI建议 ${first.title}`, { exact: true }).selectOption("adopted");
    await persisted(page, value => value.ai_results.find(r => r.issue_id === first.id)?.status, "adopted");
    await assistant.getByLabel(`处理AI建议 ${second.title}`, { exact: true }).selectOption("ignored");
    await persisted(page, value => value.ai_results.find(r => r.issue_id === second.id)?.status, "ignored");
    await page.reload();
    await page.getByText("模拟检查工具", { exact: true }).click();
    await expect(assistant.getByLabel(`改写AI建议 ${first.title}`, { exact: true })).toHaveValue(rewritten);
    await expect(assistant.getByLabel(`处理AI建议 ${first.title}`, { exact: true })).toHaveValue("adopted");
    await expect(assistant.getByLabel(`处理AI建议 ${second.title}`, { exact: true })).toHaveValue("ignored");
    await page.getByLabel("对话范围", { exact: true }).selectOption("queue");
    await expect(page.getByRole("region", { name: "编辑对话", exact: true })).toContainText("当前工作队列");
    await expect(assistant.getByRole("button", { name: "分析当前版本" })).toHaveCount(0);
    await page.getByLabel("对话范围", { exact: true }).selectOption("journal");
    await expect(page.getByRole("region", { name: "编辑对话", exact: true })).toContainText("本刊授权稿件");
    await page.getByText("模拟检查工具", { exact: true }).click();
    await page.getByLabel("稿件版本").selectOption("v2");
    await persisted(page, value => value.reading.version, "v2");
    const retained = await state(page);
    expect(retained.ai_results.find(result => result.issue_id === first.id)?.status).toBe("adopted");
    await page.getByText("模拟检查工具", { exact: true }).click();
    await page.getByLabel("对话范围", { exact: true }).selectOption("case");
    await expect(assistant.getByLabel(`改写AI建议 ${first.title}`, { exact: true })).toHaveCount(0);
    await expect(assistant).toContainText(`${manuscript.number} / V2`);
  });

  test("三种桌面尺寸、深色跟随系统、键盘焦点、200% CSS 缩放及窄屏仍可操作", async ({ page }) => {
    await login(page);
    await reset(page);
    await open(page);
    for (const size of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(size);
      await noHorizontalOverflow(page);
      await expect(page.getByLabel("搜索工作稿件")).toBeVisible();
      await page.screenshot({ path: `artifacts/workbench-queue-${size.width}.png`, fullPage: true });
    }
    await page.keyboard.press("Control+k");
    await expect(page.getByLabel("搜索工作稿件")).toBeFocused();
    await expect(page.getByLabel("搜索工作稿件")).toHaveCSS("outline-style", "solid");
    await page.getByLabel("界面主题").selectOption("dark");
    await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", "dark");
    await openProgressPreview(page);
    await page.getByRole("button", { name: "打开稿件", exact: true }).click();
    await page.screenshot({ path: "artifacts/workbench-reader-dark.png", fullPage: true });
    await page.getByLabel("界面主题").selectOption("system");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", "light");
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("[data-theme]")).toHaveAttribute("data-theme", "dark");
    await page.getByLabel("界面主题").selectOption("light");
    await page.setViewportSize({ width: 1440, height: 900 });
    // Actual document CSS zoom, recorded explicitly rather than claiming OS or
    // browser chrome zoom coverage. It exercises enlarged rendered controls.
    await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
    await page.getByRole("button", { name: "专注阅读", exact: true }).click();
    await expect(page.getByRole("button", { name: "退出专注", exact: true })).toBeVisible();
    await expect(page.getByLabel("稿件版本")).toBeVisible();
    await noHorizontalOverflow(page);
    await page.screenshot({ path: "artifacts/workbench-reader-zoom200.png", fullPage: true });
    await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
    await page.setViewportSize({ width: 390, height: 844 });
    await noHorizontalOverflow(page);
    await expect(page.getByLabel("稿件正文", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "展开工作导航", exact: true }).click();
    await expect(page.getByRole("navigation", { name: "工作视图" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("navigation", { name: "工作视图" })).toBeHidden();
    await page.screenshot({ path: "artifacts/workbench-reader-narrow.png", fullPage: true });
  });

  test("加载失败可重试，作者与审稿人 403 不泄露合成稿件", async ({ page }) => {
    await login(page);
    let unavailable = true;
    await page.route("**/api/editorial-demo", route => unavailable
      ? route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "合成验收：工作台暂时不可用" }) })
      : route.continue());
    await page.goto("/workbench");
    await expect(page.getByRole("alert").filter({ hasText: "工作台暂时不可用" })).toBeVisible();
    unavailable = false;
    await page.getByRole("button", { name: "重试加载" }).click();
    await expect(page.getByRole("table", { name: "我的稿件工作列表" })).toBeVisible();
    await page.unroute("**/api/editorial-demo");
    for (const role of ["author", "reviewer"] as const) {
      await page.goto("/");
      await page.getByRole("button", { name: "退出登录" }).click();
      await login(page, role);
      await expect(page.getByRole("navigation", { name: "工作空间" }).getByRole("button", { name: /我的工作/ })).toHaveCount(0);
      const denied = page.waitForResponse(response => response.url().endsWith("/api/editorial-demo"));
      await page.goto("/workbench");
      expect((await denied).status()).toBe(403);
      await expect(page.getByRole("alert").filter({ hasText: "只有编辑或主编" })).toBeVisible();
      await expect(page.getByText("ENV-2026-0129", { exact: false })).toHaveCount(0);
      await expect(page.getByRole("table")).toHaveCount(0);
    }
  });
});

for (const interruption of ['blur', 'lostpointercapture', 'pointercancel'] as const) test(`面板拖动遇到${interruption}停止，忽略其他指针且可再次拖动`, async ({ page }) => {
  await login(page); await reset(page); await page.setViewportSize({ width: 1920, height: 1000 }); await open(page, 'read'); await readingTools(page);
  const separator = page.getByRole('separator', { name: '调整问题面板宽度', exact: true });
  await separator.focus(); await page.keyboard.press('Home');
  const box = (await separator.boundingBox())!;
  await separator.evaluate(el => el.addEventListener('pointerdown', event => { (el as HTMLElement).dataset.pointerForTest = String((event as PointerEvent).pointerId); }, { once: true }));
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 40, box.y + box.height / 2);
  const width = await separator.getAttribute('aria-valuenow'); expect(Number(width)).toBeGreaterThan(264); expect(Number(width)).toBeLessThan(480);
  await separator.dispatchEvent('pointermove', { pointerId: 9999, clientX: box.x - 140 });
  await expect(separator).toHaveAttribute('aria-valuenow', width!);
  if (interruption === 'blur') await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  else await separator.dispatchEvent(interruption, { pointerId: Number(await separator.getAttribute('data-pointer-for-test')) });
  await page.mouse.move(box.x + box.width / 2 - 90, box.y + box.height / 2); await page.mouse.up();
  await expect(separator).toHaveAttribute('aria-valuenow', width!);
  const next = (await separator.boundingBox())!; await page.mouse.move(next.x + next.width / 2, next.y + next.height / 2); await page.mouse.down(); await page.mouse.move(next.x + next.width / 2 - 35, next.y + next.height / 2); await page.mouse.up();
  expect(Number(await separator.getAttribute('aria-valuenow'))).toBeGreaterThan(Number(width));
});
