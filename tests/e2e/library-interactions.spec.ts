import { test, expect, type Page } from "@playwright/test";
import type { Dossier, Message } from "../../apps/web/components/library/types";

async function openSynthetic(page: Page) {
  const login = await page.request.post("/api/auth/login", { data: { email: "editor@publishing.test", password: "EditorDemo2026!" } });
  expect(login.ok()).toBe(true);
  const session = await login.json();
  const creation = await page.request.post("/api/dossiers", { headers: { "X-CSRF-Token": session.csrf_token }, data: { request_id: crypto.randomUUID(), title: "交互回归 · 合成资料", source_kind: "synthetic", source_note: "全部内容为本机交互回归的合成资料", authorized_material: true } });
  expect(creation.ok()).toBe(true);
  const { dossier_id: id } = await creation.json();
  await page.goto(`/library?dossier=${id}`);
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("交互回归 · 合成资料");
  return id as string;
}

test("资料抽屉：手机焦点隔离、Escape、设置交接与宽屏恢复", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openSynthetic(page);
  await expect(page.getByRole("heading", { name: "先添加稿件全文", exact: true })).toBeVisible();
  await expect(page.getByLabel("询问当前资料")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const opener = page.getByRole("button", { name: "打开资料列表", exact: true });
  await opener.click();
  const drawer = page.getByRole("dialog", { name: "我的资料", exact: true });
  await expect(drawer.getByRole("button", { name: "关闭资料列表", exact: true })).toBeFocused();
  await expect(page.locator("#library-main").locator("..").locator("..")).toHaveAttribute("inert", "");
  await drawer.getByRole("link", { name: "返回主工作台", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(drawer.getByRole("link", { name: "Pivot", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(drawer.getByRole("link", { name: "返回主工作台", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await expect(opener).toHaveAttribute("aria-expanded", "false");
  await opener.click();
  await drawer.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "设置", exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => !!document.querySelector("dialog[open]")?.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await opener.click();
  await page.setViewportSize({ width: 1360, height: 850 });
  await expect(page.getByRole("dialog", { name: "我的资料", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("询问当前资料")).toBeEditable();
  await expect(page.locator("[inert]")).toHaveCount(0);
});

test("资料输入：Shift Enter 换行、IME 不误发、Enter 只提交一次", async ({ page }) => {
  const id = await openSynthetic(page);
  const question = page.getByLabel("询问当前资料");
  const posts: string[] = [];
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith(`/api/dossiers/${id}/chat`)) posts.push(request.postDataJSON().message); });
  await question.fill("查看资料缺项");
  await question.press("Shift+Enter");
  await expect(question).toHaveValue("查看资料缺项\n");
  await question.dispatchEvent("compositionstart");
  await question.dispatchEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true });
  await question.dispatchEvent("compositionend");
  await question.dispatchEvent("keydown", { key: "Enter", code: "Enter", keyCode: 229, bubbles: true });
  await question.dispatchEvent("keydown", { key: "Enter", code: "Enter", isComposing: true, bubbles: true });
  expect(posts).toEqual([]);
  const reply = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith(`/api/dossiers/${id}/chat`));
  await question.press("Enter");
  expect((await reply).ok()).toBe(true);
  await expect(question).toHaveValue("");
  expect(posts).toEqual(["查看资料缺项"]);
  const saved = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(saved.messages).toHaveLength(1);
  expect(saved.verified).toBe(false);
  await expect(page.getByText("邮件与关键决定须负责人确认。", { exact: true })).toBeVisible();
});

test("资料阅读：等待回复时上翻不被拉回，可主动查看最新消息", async ({ page }) => {
  const id = await openSynthetic(page);
  const snapshot = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  // Explicit synthetic UI timing fixture, not a model or persistence acceptance.
  snapshot.messages = Array.from({ length: 16 }, (_, i): Message => ({ id: `ui-history-${i}`, question: `合成历史问题 ${i}`, answer: `仅用于滚动验收的合成历史回复 ${i}。`.repeat(15), provider: "rules", version_id: snapshot.version_id, version_no: snapshot.version_no }));
  await page.route(`**/api/dossiers/${id}`, route => route.fulfill({ json: snapshot }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route(`**/api/dossiers/${id}/chat`, async route => { started = true; await gate; await route.fulfill({ json: { id: "ui-late-reply", question: "合成新问题", answer: "合成延迟回复已经到达", provider: "rules", version_id: snapshot.version_id, version_no: snapshot.version_no } }); });
  await page.reload();
  const history = page.getByLabel("资料对话历史");
  await expect(history.locator("article")).toHaveCount(16);
  await page.getByLabel("询问当前资料").fill("合成新问题");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect.poll(() => started).toBe(true);
  await history.evaluate(element => { element.scrollTop = 100; element.dispatchEvent(new Event("scroll")); });
  const top = await history.evaluate(element => element.scrollTop);
  release();
  await expect(page.getByRole("button", { name: "查看最新消息", exact: true })).toBeVisible();
  expect(Math.abs(await history.evaluate(element => element.scrollTop) - top)).toBeLessThan(3);
  await page.getByRole("button", { name: "查看最新消息", exact: true }).click();
  await expect(page.getByText("合成延迟回复已经到达", { exact: true })).toBeInViewport();
  await expect.poll(() => history.evaluate(element => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThan(3);
  await expect(page.getByRole("button", { name: "查看最新消息", exact: true })).toHaveCount(0);
});

test("原文更换：取消清空原生选择器，同一文件可重选并持久化", async ({ page }) => {
  const id = await openSynthetic(page);
  const input = page.getByLabel("原文文件", { exact: true });
  const text = "# 合成原文\n仅用于文件重新选择和版本持久化验收，不含真实稿件。";
  const file = { name: "reselect-synthetic.md", mimeType: "text/markdown", buffer: Buffer.from(text) };
  await input.setInputFiles(file);
  await page.getByRole("button", { name: "取消更换文件", exact: true }).click();
  await expect(input).toHaveValue("");
  expect(await input.evaluate(element => (element as HTMLInputElement).files?.length)).toBe(0);
  await input.setInputFiles(file);
  await expect(page.getByText("待保存：reselect-synthetic.md", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "保存为新版本", exact: true }).click();
  await expect(page.getByText("新版本已保存，请重新核对。", { exact: true })).toBeVisible();
  const saved = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(saved.file?.text).toBe(text);
  expect(saved.version_no).toBe(2);
  expect(saved.verified).toBe(false);
  await page.reload();
  await expect(page.getByText(/当前：reselect-synthetic.md/)).toBeVisible();
});
