import { test, expect, type Page } from "@playwright/test";
import type { Dossier, Session } from "../../apps/web/components/library/types";

async function login(page: Page, author = false) {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(author ? "author@publishing.test" : "editor@publishing.test");
  await page.getByLabel("密码", { exact: true }).fill(author ? "AuthorDemo2026!" : "EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(page.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
}

// Real authenticated API, database, file storage, persisted transcript and version checks.
// All content is deliberately synthetic and never enters a model or mail service.
test("内部资料真实链：录入全文作者、独立核对、新版失效、刷新与规则边界", async ({ page }) => {
  test.setTimeout(90000);
  const mutations: string[] = [];
  page.on("request", request => { if (request.method() === "POST") mutations.push(new URL(request.url()).pathname); });
  await login(page);
  await page.goto("/library");
  await page.getByRole("button", { name: "新建资料", exact: true }).first().click();
  const title = `合成内部资料浏览器验收 ${Date.now()}`;
  await page.getByLabel("题名", { exact: true }).fill(title);
  await page.getByLabel("来源与授权说明", { exact: true }).fill("全部内容为本地自动化验收生成的授权合成资料。");
  await page.getByRole("checkbox", { name: /我确认仅录入合成/ }).check();
  const creation = page.waitForResponse(response => response.url().endsWith("/api/dossiers") && response.request().method() === "POST");
  await page.getByRole("button", { name: "创建资料", exact: true }).click();
  const created = await creation; expect(created.status()).toBe(200);
  const { dossier_id: id } = await created.json();
  await expect(page).toHaveURL(new RegExp(`dossier=${id}`));
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue(title);
  await page.getByLabel("摘要", { exact: true }).fill("这是一份完全合成的研究摘要，用于验证内部资料工作区的真实作者元数据、完整文本保存、版本追溯与负责人独立核对流程，不包含保密稿件或真实个人资料。");
  await page.getByLabel("关键词", { exact: true }).fill("合成资料, 版本追溯");
  await page.getByRole("button", { name: "添加作者", exact: true }).click();
  const first = page.getByRole("group", { name: "作者 1", exact: true });
  await first.getByLabel("姓名", { exact: true }).fill("合成作者甲");
  await first.getByLabel("邮箱", { exact: true }).fill("synthetic-first@example.test");
  await first.getByLabel("机构（每行一项）", { exact: true }).fill("合成机构甲\n合成机构乙");
  await first.getByLabel("作者贡献（选填，每行一项）", { exact: true }).fill("合成方法设计\n合成数据核对");
  await first.getByLabel("ORCID（选填，未认证）", { exact: true }).fill("0000-0002-1825-0097");
  await first.getByLabel("作者 / ORCID 来源", { exact: true }).fill("完全合成的作者输入记录，仅验证格式，不认证身份。");
  await first.getByRole("radio", { name: "通讯作者", exact: true }).check();
  await page.getByRole("button", { name: "添加作者", exact: true }).click();
  const second = page.getByRole("group", { name: "作者 2", exact: true });
  await second.getByLabel("姓名", { exact: true }).fill("合成作者乙");
  await second.getByLabel("机构（每行一项）", { exact: true }).fill("合成第二机构");
  await second.getByLabel("作者 / ORCID 来源", { exact: true }).fill("第二位作者亦为完全合成记录。");
  await second.getByRole("button", { name: "上移作者 2", exact: true }).click();
  await expect(first.getByLabel("姓名", { exact: true })).toHaveValue("合成作者乙");
  await expect(second.getByRole("radio", { name: "通讯作者", exact: true })).toBeChecked();
  const fullText = "# 完全合成的研究全文\n这份完整正文与摘要独立存储，不含真实保密信息。\n".repeat(50) + "正文末尾合成定位标记 END-OF-SYNTHETIC-DOSSIER";
  await page.getByLabel("原文文件", { exact: true }).setInputFiles({ name: "synthetic-dossier.md", mimeType: "text/markdown", buffer: Buffer.from(fullText, "utf8") });
  await page.getByRole("button", { name: "保存为新版本", exact: true }).click();
  await expect(page.getByText("新版本已保存，请重新核对。", { exact: true })).toBeVisible();
  let current = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(current.data.authors.map(author => author.name)).toEqual(["合成作者乙", "合成作者甲"]);
  expect(current.data.authors[1].corresponding).toBe(true); expect(current.data.authors[1].contributions).toEqual(["合成方法设计", "合成数据核对"]); expect(current.missing).toEqual([]);
  expect(current.file?.text).toBe(fullText); expect(current.file?.sha256).toMatch(/^[a-f0-9]{64}$/);
  const download = await page.request.get(current.file!.download_url); expect(download.status()).toBe(200); expect(await download.text()).toBe(fullText);
  await page.reload(); await expect(page.getByLabel("题名", { exact: true })).toHaveValue(title);
  await expect(page.locator('textarea[name="author-1-contributions"]')).toHaveValue("合成方法设计\n合成数据核对");
  await page.getByRole("link", { name: "核对本版资料", exact: true }).click();
  await expect(page.getByText("合成方法设计", { exact: true })).toBeVisible();
  await expect(page.getByText("合成数据核对", { exact: true })).toBeVisible();
  const firstVersionId = current.version_id;
  await expect(page).toHaveURL(new RegExp(`/library/review/${firstVersionId}`));
  const acknowledgement = page.getByRole("checkbox", { name: /我已逐项核对/ });
  await expect(acknowledgement).not.toBeChecked();
  await expect(page.getByRole("button", { name: "确认本版资料", exact: true })).toBeDisabled();
  await expect(page.getByText(/正文末尾合成定位标记 END-OF-SYNTHETIC-DOSSIER/)).toBeVisible();
  await expect(page.getByText(current.content_digest, { exact: true })).toHaveCount(1);
  await acknowledgement.check(); await page.getByRole("button", { name: "确认本版资料", exact: true }).click();
  await expect(page.getByText("当前版本已由本人核对。", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "返回资料", exact: true }).click();
  await page.getByLabel("题名", { exact: true }).fill(`${title} 修订`);
  await page.getByRole("button", { name: "保存为新版本", exact: true }).click();
  await expect(page.getByText("新版本已保存，请重新核对。", { exact: true })).toBeVisible();
  current = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(current.verified).toBe(false); expect(current.version_id).not.toBe(firstVersionId); expect(current.file?.text).toBe(fullText); expect(current.data.authors[1].contributions).toEqual(["合成方法设计", "合成数据核对"]);
  await page.getByLabel("询问当前资料").fill("请替我确认资料、发送录用邮件并正式发表。");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText(/对话不能代替负责人核对，也不能发送邮件或作编辑决定/)).toBeVisible();
  await page.reload(); await expect(page.getByText(/对话不能代替负责人核对，也不能发送邮件或作编辑决定/)).toBeVisible();
  const afterChat = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(afterChat.data.authors[1].contributions).toEqual(["合成方法设计", "合成数据核对"]);
  expect(afterChat.verified).toBe(false); expect(afterChat.version_id).toBe(current.version_id); expect(afterChat.messages.at(-1)?.provider).toBe("rules");
  expect(mutations.filter(path => path.endsWith("/confirm"))).toHaveLength(1);
  expect(mutations.filter(path => path !== "/api/auth/login" && !path.startsWith("/api/dossiers"))).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("询问当前资料")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.getByRole("button", { name: "打开资料列表", exact: true }).click();
  await expect(page.getByRole("link", { name: new RegExp(`${title} 修订`) }).first()).toBeVisible();
  await page.getByRole("button", { name: "关闭资料列表", exact: true }).click();
  await page.goto(`/library/review/${firstVersionId}?dossier=${id}`);
  await expect(page.getByText("这是历史版本，只可查看。请返回资料核对当前版本。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "本版已核对", exact: true })).toBeDisabled();
});

test("内部资料真实角色边界：作者返回可用登录入口", async ({ page }) => {
  await login(page, true); await page.goto("/library");
  await expect(page.getByRole("alert").filter({ hasText: "仅向编辑和主编开放" })).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "返回登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
});

const ID = "10000000-0000-4000-8000-000000000001";
const OTHER = "10000000-0000-4000-8000-000000000002";
const VERSION = "20000000-0000-4000-8000-000000000001";
const syntheticSession: Session = { user: { id: "synthetic-editor", name: "合成编辑", email: "editor@example.test", role: "editor" }, journal: { id: "synthetic-journal", name: "合成期刊" }, csrf_token: "synthetic-csrf" };
function syntheticDossier(id = ID): Dossier {
  return { id, revision: 1, version_id: VERSION, version_no: 1, content_digest: "a".repeat(64), is_current: true, verified: false, verification: null, data: { title: id === ID ? "合成资料甲" : "合成资料乙", abstract: "完全合成摘要", language: "zh", keywords: [], authors: [], source_kind: "synthetic", source_note: "完全合成的界面测试记录" }, file: null, missing: [{ field: "file", message: "请上传完整正文" }], versions: [{ id: VERSION, number: 1, title: "合成资料", created_at: "2026-11-03T00:00:00Z", verified: false }], messages: [] };
}
async function fixtures(page: Page) {
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/publishing/session") return route.fulfill({ json: syntheticSession });
    if (route.request().method() !== "GET") throw new Error(`Unexpected mutation: ${path}`);
    if (path === "/api/dossiers") return route.fulfill({ json: { items: [ID, OTHER].map(id => ({ id, title: syntheticDossier(id).data.title, revision: 1, version_id: VERSION, version_no: 1, verified: false, updated_at: "2026-11-03T00:00:00Z" })) } });
    return route.fulfill({ json: syntheticDossier(path.includes(OTHER) ? OTHER : ID) });
  });
}

test("资料 UI：未保存输入保护且缺项不能确认", async ({ page }) => {
  await fixtures(page); await page.goto(`/library?dossier=${ID}`);
  await page.getByLabel("题名", { exact: true }).fill("未保存的合成题名");
  let prompts = 0; page.on("dialog", async dialog => { prompts++; await dialog.dismiss(); });
  await page.getByRole("link", { name: /合成资料乙/ }).click();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("未保存的合成题名"); expect(prompts).toBe(1);
  page.removeAllListeners("dialog"); page.on("dialog", async dialog => { await dialog.accept(); });
  await page.reload();
  await page.getByRole("link", { name: "核对本版资料", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /我已逐项核对/ })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: /我已逐项核对/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "确认本版资料", exact: true })).toBeDisabled();
});

test("资料 UI：网络失败清空旧历史并以相同 UUID 重试", async ({ page }) => {
  await fixtures(page); const requests: { request_id: string }[] = [];
  await page.route(`**/api/dossiers/${ID}/assist`, route => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) return route.abort();
    return route.fulfill({ json: { id: "synthetic-turn", question: "查看缺项", answer: "合成规则回复", provider: "rules", version_id: VERSION, version_no: 1 } });
  });
  await page.goto(`/library?dossier=${ID}`);
  await page.getByLabel("询问当前资料").fill("查看缺项"); await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试原请求", exact: true }).click();
  await expect(page.getByText("合成规则回复", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2); expect(requests[0].request_id).toBe(requests[1].request_id);
});

test("资料 UI：慢旧回复不覆盖新选定资料，404 清空旧材料", async ({ page }) => {
  await fixtures(page); let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; }); let started = false;
  await page.route(`**/api/dossiers/${ID}/assist`, async route => { started = true; await gate; return route.fulfill({ json: { id: "old-turn", question: "旧资料状态", answer: "旧资料迟到的回复", provider: "rules", version_id: VERSION, version_no: 1 } }); });
  await page.goto(`/library?dossier=${ID}`);
  await page.getByLabel("询问当前资料").fill("旧资料状态"); await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect.poll(() => started).toBe(true);
  await page.getByRole("link", { name: /合成资料乙/ }).click();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("合成资料乙");
  release(); await expect(page.getByRole("button", { name: "发送", exact: true })).not.toHaveText("回复中…");
  await expect(page.getByText("旧资料迟到的回复", { exact: true })).toHaveCount(0);
  await page.route(`**/api/dossiers/${ID}`, route => route.fulfill({ status: 404, json: { detail: "合成资料权限已撤销" } }));
  await page.getByRole("link", { name: /合成资料甲/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: "合成资料权限已撤销" })).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await expect(page.getByText("合成资料乙", { exact: true })).toHaveCount(0);
});
