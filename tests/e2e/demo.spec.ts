import { test as base, expect, type Locator, type Page } from "@playwright/test";

const demoPath = process.env.DEMO_PATH || "/demo";
const storageKey = "publishing-os-public-demo-v1";
const firstId = "POS-2026-0012";
const secondId = "POS-2026-0018";
const firstTitle = "开放科学实践与研究数据可复现性：一项多中心方法研究";
const secondTitle = "城市绿色空间对夏季热环境的影响：一项模拟观察研究";

type SavedDemo = {
  selected: string;
  drafts: Record<string, string>;
  threads: Record<string, { role: string; text: string }[]>;
  manuscripts: {
    id: string; title: string; stage: string; abstract: string;
    authors: { name: string; affiliation: string; email: string; orcid: string }[];
    paragraphs: { id: string; text: string }[];
  }[];
};

// The public demo must remain usable without the business API, including reloads.
// Abort an accidental API call as well as recording it, so a regression cannot
// reach a real mutation endpoint while the independent demo is being tested.
const test = base.extend<{ apiRequests: string[] }>({
  apiRequests: [async ({ page }, use) => {
    const requests: string[] = [];
    page.on("request", request => {
      if (/^\/api(?:\/|$)/.test(new URL(request.url()).pathname)) requests.push(`${request.method()} ${request.url()}`);
    });
    await page.route(url => /^\/api(?:\/|$)/.test(url.pathname), route => route.abort());
    await use(requests);
    expect(requests, "独立产品演示不应访问任何 /api 接口").toEqual([]);
  }, { auto: true }],
});

const conversation = (page: Page) => page.getByRole("main");
const log = (page: Page) => conversation(page).getByRole("log");
const composer = (page: Page) => conversation(page).getByRole("textbox", { name: "对话消息", exact: true });
const materials = (page: Page) => page.getByRole("complementary", { name: "当前稿件资料", exact: true });
const work = (page: Page) => page.getByRole("complementary", { name: "我的工作与日历", exact: true });

async function saved(page: Page): Promise<SavedDemo> {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key) || "null"), storageKey);
}
async function send(page: Page, text: string) {
  await composer(page).fill(text);
  await conversation(page).getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(log(page).getByRole("article").filter({ hasText: text })).toBeVisible();
  await expect(composer(page)).toHaveValue("");
}
async function inViewport(control: Locator) {
  await expect(control).toBeVisible();
  await expect(control).toBeInViewport({ ratio: 1 });
}
async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

test.describe("独立产品演示 · 本地资料、对话与安全边界", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(demoPath);
    await expect(composer(page)).toBeVisible();
    await expect(log(page)).toHaveAccessibleName(`${firstId}稿件对话`);
    await expect.poll(async () => saved(page)).not.toBeNull();
  });

  test("当前稿件方法问答关联原文，公开引用提供明确来源", async ({ page }) => {
    const context = materials(page);
    await expect(context.getByRole("heading", { name: firstTitle, exact: true })).toBeVisible();
    await context.getByRole("tab", { name: "作者", exact: true }).click();
    await conversation(page).getByRole("button", { name: "检查方法", exact: true }).click();
    const reply = log(page).getByRole("article").last();
    await expect(reply).toContainText("任务纳入与排除标准");
    await expect(reply).toContainText("数据划分的随机种子");
    await reply.getByRole("button", { name: "方法", exact: true }).click();
    await expect(context.getByRole("tab", { name: "稿件", exact: true })).toHaveAttribute("aria-selected", "true");
    const method = context.getByRole("tabpanel", { name: "稿件", exact: true }).locator("section").filter({ has: page.getByRole("heading", { name: "方法", exact: true }) });
    await expect(method.getByRole("heading", { name: "方法", exact: true })).toBeInViewport();
    await expect(method).toContainText("三个虚构中心构建128项模拟任务");
    await method.getByRole("button", { name: "围绕此段提问", exact: true }).click();
    await expect(composer(page)).toHaveValue(/我想讨论“方法”：本研究在三个虚构中心/);
    await expect(composer(page)).toBeFocused();
    await composer(page).clear();
    await conversation(page).getByRole("button", { name: "查看参考文献", exact: true }).click();
    const referenceReply = log(page).getByRole("article").last();
    await expect(referenceReply).toContainText("10.1038/sdata.2016.18");
    await referenceReply.getByRole("button", { name: "公开文献", exact: true }).click();
    const evidence = context.getByRole("tabpanel", { name: "证据", exact: true });
    await expect(evidence.getByRole("link", { name: "出版社原文" })).toHaveAttribute("href", "https://www.nature.com/articles/sdata201618");
    await expect(evidence.getByRole("link", { name: "Crossref 元数据" })).toHaveAttribute("href", "https://api.crossref.org/works/10.1038/sdata.2016.18");
    await expect(evidence).toContainText("不证明本稿结论，非实时检索");
  });

  test("主对话与各稿件的消息、草稿隔离，刷新恢复所选稿件及输入", async ({ page }) => {
    const firstMessage = "概括这篇稿件：稿件一独有记录";
    const mainMessage = "今天有哪些工作？主对话独有记录";
    await send(page, firstMessage);
    await composer(page).fill("第一篇尚未发送的草稿");
    await work(page).getByRole("button", { name: "主对话", exact: true }).click();
    await expect(composer(page)).toHaveValue("");
    await expect(log(page)).toHaveAccessibleName("主对话记录");
    await expect(log(page)).not.toContainText(firstMessage);
    await send(page, mainMessage);
    await expect(log(page).getByRole("article").last()).toContainText("3 篇演示稿件");
    await composer(page).fill("全刊工作的未发送草稿");
    await work(page).getByRole("button", { name: /^城市热岛与绿色空间/ }).click();
    await expect(composer(page)).toHaveValue("");
    await expect(log(page)).not.toContainText(firstMessage);
    await expect(log(page)).not.toContainText(mainMessage);
    await composer(page).fill("第二篇尚未发送的草稿");
    await expect.poll(async () => (await saved(page)).drafts[secondId]).toBe("第二篇尚未发送的草稿");
    await page.reload();
    await expect(log(page)).toHaveAccessibleName(`${secondId}稿件对话`);
    await expect(composer(page)).toHaveValue("第二篇尚未发送的草稿");
    await work(page).getByRole("button", { name: /^开放科学与数据可复现性/ }).click();
    await expect(composer(page)).toHaveValue("第一篇尚未发送的草稿");
    await expect(log(page)).toContainText(firstMessage);
    await expect(log(page)).not.toContainText(mainMessage);
    await work(page).getByRole("button", { name: "主对话", exact: true }).click();
    await expect(composer(page)).toHaveValue("全刊工作的未发送草稿");
    await expect(log(page)).toContainText(mainMessage);
    await expect(log(page)).not.toContainText(firstMessage);
    await expect.poll(async () => (await saved(page)).selected).toBe("main");
    await page.reload();
    await expect(log(page)).toHaveAccessibleName("主对话记录");
    await expect(composer(page)).toHaveValue("全刊工作的未发送草稿");
  });

  test("题名、摘要及作者元数据保存到浏览器，刷新后新回答使用更新资料", async ({ page }) => {
    const context = materials(page);
    const title = "合成数据透明报告与可复现性：更新演示稿";
    const abstract = "这是人工编辑并保存的合成摘要，用于核对刷新与后续问答。";
    await context.getByRole("button", { name: "编辑稿件资料", exact: true }).click();
    await context.getByRole("textbox", { name: "题名", exact: true }).fill(title);
    await context.getByRole("textbox", { name: "摘要", exact: true }).fill(abstract);
    const author = context.getByRole("group", { name: "作者 1", exact: true });
    await author.getByRole("textbox", { name: "姓名", exact: true }).fill("演示周言");
    await author.getByRole("textbox", { name: "机构", exact: true }).fill("合成开放研究中心");
    await author.getByRole("textbox", { name: "邮箱", exact: true }).fill("demo-author@example.test");
    await author.getByRole("textbox", { name: "ORCID（手工录入，未经认证）", exact: true }).fill("0000-0000-0000-000X");
    await context.getByRole("button", { name: "保存演示资料", exact: true }).click();
    await expect(conversation(page).getByRole("status")).toContainText("演示资料已保存到当前浏览器");
    await expect.poll(async () => (await saved(page)).manuscripts.find(m => m.id === firstId)?.title).toBe(title);
    await page.reload();
    await expect(context.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await expect(context.getByRole("tabpanel", { name: "稿件", exact: true })).toContainText(abstract);
    await context.getByRole("tab", { name: "作者", exact: true }).click();
    const authors = context.getByRole("tabpanel", { name: "作者", exact: true });
    for (const value of ["演示周言", "合成开放研究中心", "demo-author@example.test", "0000-0000-0000-000X", "未认证"]) await expect(authors).toContainText(value);
    await conversation(page).getByRole("button", { name: "概括这篇稿件", exact: true }).click();
    await expect(log(page).getByRole("article").last()).toContainText(title);
    await expect(log(page).getByRole("article").last()).toContainText(abstract);
    const persisted = (await saved(page)).manuscripts.find(m => m.id === firstId)!;
    expect(persisted.authors[0]).toEqual({ name: "演示周言", affiliation: "合成开放研究中心", email: "demo-author@example.test", orcid: "0000-0000-0000-000X" });
    expect(persisted.paragraphs.find(p => p.id === "abstract")?.text).toBe(abstract);
  });

  test("新演示稿创建后出现在待办，正文与作者在刷新后保留", async ({ page }) => {
    await work(page).getByRole("button", { name: "录入演示稿件", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "录入演示稿件", exact: true });
    const title = "合成生态观测的完整演示稿";
    const body = "研究背景：这是公开合成材料。\n方法：只使用模拟观测，不涉及真实参与者。\n结果：此文本用于检验本地持久保存。";
    await dialog.getByRole("textbox", { name: "稿件题名", exact: true }).fill(title);
    await dialog.getByRole("textbox", { name: "示例作者姓名", exact: true }).fill("合成作者禾木");
    await dialog.getByRole("textbox", { name: "稿件正文", exact: true }).fill(body);
    await dialog.getByRole("button", { name: "创建本地演示稿件", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(materials(page).getByRole("heading", { name: title, exact: true })).toBeVisible();
    await expect(materials(page).getByRole("tabpanel", { name: "稿件", exact: true })).toContainText(body);
    await expect.poll(async () => (await saved(page)).manuscripts.length).toBe(4);
    const created = (await saved(page)).manuscripts.find(m => m.title === title)!;
    expect(created.id).toMatch(/^DEMO-/);
    expect(created.stage).toBe("投稿准备");
    expect(created.authors[0].name).toBe("合成作者禾木");
    expect(created.paragraphs.find(p => p.id === "body")?.text).toBe(body);
    await page.reload();
    await expect(log(page)).toHaveAccessibleName(`${created.id}稿件对话`);
    await expect(materials(page).getByRole("tabpanel", { name: "稿件", exact: true })).toContainText(body);
    await work(page).getByRole("button", { name: /^开放科学与数据可复现性/ }).click();
    await work(page).getByRole("button", { name: new RegExp(`^${title}`) }).click();
    await materials(page).getByRole("tab", { name: "作者", exact: true }).click();
    await expect(materials(page).getByRole("tabpanel", { name: "作者", exact: true })).toContainText("合成作者禾木");
  });

  test("日历选择无待办日期显示空列表，清除筛选恢复稿件", async ({ page }) => {
    const sidebar = work(page);
    const calendar = sidebar.getByRole("region", { name: "稿件截止日日历", exact: true });
    const emptyDay = calendar.getByRole("button", { name: /，无待办$/ }).first();
    await emptyDay.click();
    await expect(emptyDay).toHaveAttribute("aria-pressed", "true");
    await expect(sidebar).toContainText("这一天没有匹配的待办");
    await expect(sidebar.getByRole("button", { name: /^开放科学与数据可复现性/ })).toHaveCount(0);
    await expect(sidebar.getByRole("button", { name: /^城市热岛与绿色空间/ })).toHaveCount(0);
    await expect(sidebar.getByRole("button", { name: /^科学传播中的视觉叙事/ })).toHaveCount(0);
    // Filtering the work list must not silently replace the open conversation.
    await expect(log(page)).toHaveAccessibleName(`${firstId}稿件对话`);
    await calendar.getByRole("button", { name: /^清除日期筛选/ }).click();
    await expect(sidebar.getByRole("button", { name: /^开放科学与数据可复现性/ })).toBeVisible();
    await expect(sidebar.getByRole("button", { name: /^城市热岛与绿色空间/ })).toBeVisible();
    await expect(sidebar.getByRole("button", { name: /^科学传播中的视觉叙事/ })).toBeVisible();
    await expect(calendar.getByRole("button", { name: /^清除日期筛选/ })).toHaveCount(0);
  });

  test("发邮件与录用请求明确拒绝，所有稿件阶段和资料保持原样", async ({ page }) => {
    const before = (await saved(page)).manuscripts;
    for (const request of ["请给作者发邮件通知审稿结果", "请直接批准并正式录用这篇稿件"]) {
      await send(page, request);
      await expect(log(page).getByRole("article").last()).toContainText("对话不能发送邮件、批准或作出正式编辑决定");
      await expect(log(page).getByRole("article").last()).toContainText("没有改变稿件状态");
    }
    await expect.poll(async () => (await saved(page)).threads[firstId]?.length).toBe(5);
    expect((await saved(page)).manuscripts).toEqual(before);
    await page.reload();
    await expect(log(page)).toContainText("请直接批准并正式录用这篇稿件");
    await expect(materials(page)).toContainText("编辑初筛");
    expect((await saved(page)).manuscripts).toEqual(before);
  });

  test("资料tabs支持方向键、Home与End，焦点和关联面板同步", async ({ page }) => {
    const context = materials(page);
    const tabs = context.getByRole("tablist", { name: "稿件资料类型", exact: true });
    await tabs.getByRole("tab", { name: "稿件", exact: true }).focus();
    for (const [key, label] of [["ArrowRight", "作者"], ["ArrowRight", "证据"], ["ArrowRight", "稿件"], ["ArrowLeft", "证据"], ["Home", "稿件"], ["End", "证据"]]) {
      await page.keyboard.press(key);
      const active = tabs.getByRole("tab", { name: label, exact: true });
      await expect(active).toBeFocused();
      await expect(active).toHaveAttribute("aria-selected", "true");
      await expect(active).toHaveAttribute("tabindex", "0");
      await expect(tabs.getByRole("tab", { selected: true })).toHaveCount(1);
      await expect(context.getByRole("tabpanel", { name: label, exact: true })).toBeVisible();
      expect(await active.getAttribute("aria-controls")).toBe(await context.getByRole("tabpanel", { name: label, exact: true }).getAttribute("id"));
    }
    await page.keyboard.press("Tab");
    await expect(context.getByRole("tabpanel", { name: "证据", exact: true })).toBeFocused();
  });

  test("375px窄屏输入与发送可见，工作和资料抽屉可操作并可关闭", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await noHorizontalOverflow(page);
    await inViewport(composer(page));
    await composer(page).fill("窄屏草稿");
    await inViewport(conversation(page).getByRole("button", { name: "发送消息", exact: true }));
    await conversation(page).getByRole("button", { name: "打开我的工作", exact: true }).click();
    const tasks = page.getByRole("dialog", { name: "我的工作", exact: true });
    await expect(tasks).toBeVisible();
    await tasks.getByRole("button", { name: /^城市热岛与绿色空间/ }).click();
    await expect(tasks).toBeHidden();
    await expect(log(page)).toHaveAccessibleName(`${secondId}稿件对话`);
    await expect(composer(page)).toHaveValue("");
    await inViewport(composer(page));
    await conversation(page).getByRole("button", { name: "资料", exact: true }).click();
    const context = page.getByRole("dialog", { name: "稿件资料", exact: true });
    await expect(context.getByRole("heading", { name: secondTitle, exact: true })).toBeVisible();
    await context.getByRole("tab", { name: "作者", exact: true }).click();
    await expect(context.getByRole("tabpanel", { name: "作者", exact: true })).toContainText("林清");
    await page.keyboard.press("Escape");
    await expect(context).toBeHidden();
    await conversation(page).getByRole("button", { name: "检查方法", exact: true }).click();
    await log(page).getByRole("article").last().getByRole("button", { name: "方法", exact: true }).click();
    await expect(context).toBeVisible();
    const method = context.getByRole("tabpanel", { name: "稿件", exact: true }).locator("section").filter({ has: page.getByRole("heading", { name: "方法", exact: true }) });
    await expect(method).toContainText("20个合成观测点");
    await method.getByRole("button", { name: "围绕此段提问", exact: true }).click();
    await expect(context).toBeHidden();
    await expect(composer(page)).toHaveValue(/我想讨论“方法”/);
    await inViewport(composer(page));
    await noHorizontalOverflow(page);
  });

  test("恶意HTML在对话和录入稿件中保留为纯文本，刷新不会执行", async ({ page }) => {
    const payload = '<img src=x onerror="window.__demoXss=true"><script>window.__demoXss=true</script>';
    await send(page, payload);
    await expect(log(page).getByRole("article").filter({ hasText: payload })).toContainText(payload);
    await expect(log(page).locator("img, script")).toHaveCount(0);
    await work(page).getByRole("button", { name: "录入演示稿件", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "录入演示稿件", exact: true });
    await dialog.getByRole("textbox", { name: "稿件题名", exact: true }).fill(`合成安全演示 ${payload}`);
    await dialog.getByRole("textbox", { name: "示例作者姓名", exact: true }).fill("合成安全作者");
    await dialog.getByRole("textbox", { name: "稿件正文", exact: true }).fill(payload);
    await dialog.getByRole("button", { name: "创建本地演示稿件", exact: true }).click();
    await expect(materials(page).getByRole("heading", { name: `合成安全演示 ${payload}`, exact: true })).toBeVisible();
    await expect(materials(page).getByRole("tabpanel", { name: "稿件", exact: true })).toContainText(payload);
    await expect(materials(page).locator("img, script")).toHaveCount(0);
    await expect.poll(async () => (await saved(page)).manuscripts.find(m => m.title === `合成安全演示 ${payload}`)?.paragraphs.find(p => p.id === "body")?.text).toBe(payload);
    await page.reload();
    await expect(materials(page).getByRole("tabpanel", { name: "稿件", exact: true })).toContainText(payload);
    await expect(materials(page).locator("img, script")).toHaveCount(0);
    expect(await page.evaluate(() => (window as Window & { __demoXss?: boolean }).__demoXss)).toBeUndefined();
  });

  test("超过千字的新稿仅编辑题名保留完整正文，修改摘要使历史引用过期", async ({ page }) => {
    const title = "长正文独立保存的合成演示稿";
    const revisedTitle = "只修改题名后的长正文合成演示稿";
    const body = Array.from({ length: 45 }, (_, i) => `第${i + 1}段：这是公开合成的完整研究材料，用于检验保存题名时不会截断或覆盖正文。`).join("\n") + "\n全文结束标记：合成正文保持完整。";
    expect(body.length).toBeGreaterThan(1000);
    await work(page).getByRole("button", { name: "录入演示稿件", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "录入演示稿件", exact: true });
    await dialog.getByRole("textbox", { name: "稿件题名", exact: true }).fill(title);
    await dialog.getByRole("textbox", { name: "示例作者姓名", exact: true }).fill("合成长文作者");
    await dialog.getByRole("textbox", { name: "稿件正文", exact: true }).fill(body);
    await dialog.getByRole("button", { name: "创建本地演示稿件", exact: true }).click();
    const context = materials(page);
    await expect(context.getByRole("heading", { name: title, exact: true })).toBeVisible();
    // Keep the initial welcome as a genuine history snapshot before editing.
    await conversation(page).getByRole("button", { name: "概括这篇稿件", exact: true }).click();
    const historicalAbstract = log(page).getByRole("article").first().getByRole("button", { name: "摘要", exact: true });
    await context.getByRole("button", { name: "编辑稿件资料", exact: true }).click();
    await context.getByRole("textbox", { name: "题名", exact: true }).fill(revisedTitle);
    await context.getByRole("button", { name: "保存演示资料", exact: true }).click();
    await expect.poll(async () => (await saved(page)).manuscripts.find(m => m.title === revisedTitle)?.paragraphs.find(p => p.id === "body")?.text).toBe(body);
    await page.reload();
    await expect(context.getByRole("heading", { name: revisedTitle, exact: true })).toBeVisible();
    const fullText = context.getByRole("tabpanel", { name: "稿件", exact: true }).locator("section").filter({ has: page.getByRole("heading", { name: "录入正文", exact: true }) });
    await expect(fullText.locator("p")).toHaveText(body);
    await context.getByRole("button", { name: "编辑稿件资料", exact: true }).click();
    const revisedAbstract = "独立录入的合成摘要，与此前待补充的摘要不同，不替代完整正文。";
    await context.getByRole("textbox", { name: "摘要", exact: true }).fill(revisedAbstract);
    await context.getByRole("button", { name: "保存演示资料", exact: true }).click();
    await context.getByRole("tab", { name: "作者", exact: true }).click();
    await historicalAbstract.click();
    await expect(conversation(page).getByRole("status")).toContainText("这条历史回答引用的资料已修改");
    await expect(context.getByRole("tab", { name: "作者", exact: true })).toHaveAttribute("aria-selected", "true");
    const manuscript = (await saved(page)).manuscripts.find(m => m.title === revisedTitle)!;
    expect(manuscript.abstract).toBe(revisedAbstract);
    expect(manuscript.paragraphs.find(p => p.id === "body")?.text).toBe(body);
  });

  test("同一方法引用可重复定位，方法修改后历史引用过期且新回答使用新正文", async ({ page }) => {
    const context = materials(page);
    const panel = context.getByRole("tabpanel", { name: "稿件", exact: true });
    const method = panel.locator("section").filter({ has: page.getByRole("heading", { name: "方法", exact: true }) });
    const heading = method.getByRole("heading", { name: "方法", exact: true });
    const originalMethod = await method.locator("p").innerText();
    await conversation(page).getByRole("button", { name: "检查方法", exact: true }).click();
    const oldReply = log(page).getByRole("article").filter({ hasText: originalMethod });
    const citation = oldReply.getByRole("button", { name: "方法", exact: true });
    await citation.click();
    await expect(heading).toBeInViewport();
    await panel.hover();
    await page.mouse.wheel(0, 3000);
    await expect(heading).not.toBeInViewport();
    await citation.click();
    await expect(heading).toBeInViewport();
    await expect(method).toContainText(originalMethod);
    await context.getByRole("button", { name: "编辑稿件资料", exact: true }).click();
    const revisedMethod = "修订方法材料：使用60项合成任务，明确列出纳入标准与排除标准，随机种子为17；这些仍是演示材料。";
    await context.locator('textarea[name="paragraph-methods"]').fill(revisedMethod);
    await context.getByRole("button", { name: "保存演示资料", exact: true }).click();
    await expect.poll(async () => (await saved(page)).manuscripts.find(m => m.id === firstId)?.paragraphs.find(p => p.id === "methods")?.text).toBe(revisedMethod);
    await context.getByRole("tab", { name: "作者", exact: true }).click();
    await citation.click();
    await expect(conversation(page).getByRole("status")).toContainText("这条历史回答引用的资料已修改");
    await expect(context.getByRole("tab", { name: "作者", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(oldReply).toContainText(originalMethod);
    await send(page, "请检查方法，使用刚保存的修订材料");
    const newReply = log(page).getByRole("article").last();
    await expect(newReply).toContainText(revisedMethod);
    await expect(newReply).not.toContainText(originalMethod);
    await newReply.getByRole("button", { name: "方法", exact: true }).click();
    await expect(heading).toBeInViewport();
    await expect(method.locator("p")).toHaveText(revisedMethod);
  });
});
