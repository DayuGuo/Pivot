import { test, expect, type Page } from "@playwright/test";
import type { ChatMessage, Detail, Proposal, PublishingSession } from "../../apps/web/components/publishing/types";

// Network-controlled UI regressions only. These fixtures never write business records.
const MID = "10000000-0000-4000-8000-000000000001";
const OTHER = "10000000-0000-4000-8000-000000000002";
const PID = "20000000-0000-4000-8000-000000000001";
const session: PublishingSession = { user: { id: "ui-recovery-user", name: "合成制作负责人", email: "fixture@publishing.test", role: "production_editor" }, journal: { id: "fixture-journal", name: "合成界面测试期刊" }, csrf_token: "ui-only", model: { provider: "mock", available: true }, synthetic_only: true, email_send_enabled: false };
const metadata = { schema_version: 1 as const, title: "合成界面恢复稿件", abstract: "只用于受控网络界面测试。", language: "zh" as const, article_type: "research_article" as const, keywords: ["合成"], authors: [], funding_statement: "" };
const detail: Detail = { id: MID, number: "UI-RECOVERY-1", title: metadata.title, stage: "production", stage_label: "出版制作", revision: 1, is_legacy: false, is_owner: false, capabilities: [], current_version_id: null, draft_version_id: null, accepted_version_id: "accepted-ui-version", own_tasks: [], created_at: "2026-11-03T00:00:00Z", submitted_at: null, versions: [], version: null, missing: [], can_edit_intake: false, field_sources: {}, timeline: [], allowed_actions: [], staff_review: null, return_request: null, production: { mode: "production", accepted_version_id: "accepted-ui-version", acceptance_decision_id: "ui-decision", metadata_snapshot: metadata, metadata_digest: "a".repeat(64), active_package_id: null, packages: [], preview: null, can_upload_proof: true, draft_file: null, accepted_materials: [] } };
const proposal: Proposal = { id: PID, manuscript_id: MID, number: detail.number, action_type: "send_proof", digest: "b".repeat(64), base_revision: 1, payload: { action: "send_proof", stage: "production", version: null, schema_version: 1, synthetic_only: true }, evidence: {}, created_at: "2026-11-03T00:00:00Z", expires_at: "2099-11-03T00:00:00Z", status: "pending", confirmation: null };
const message = (id: string, content: string): ChatMessage => ({ id, content, role: "assistant", provider: "mock", created_at: "2026-11-03T00:00:00Z", references: [], tool_receipts: [], action: null });
function gate() { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); return { promise, release }; }
async function fixtures(page: Page) {
  await page.route("**/api/publishing/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") throw new Error(`Unexpected real mutation: ${path}`);
    if (path.endsWith("/session")) return route.fulfill({ json: session });
    if (path.endsWith("/workspace")) return route.fulfill({ json: { submissions: [detail, { ...detail, id: OTHER, number: "UI-RECOVERY-2", title: "另一篇合成稿件" }], tasks: [], counts: { actionable: 0, waiting: 0 }, synthetic_only: true } });
    if (path.includes("/manuscripts/")) return route.fulfill({ json: { ...detail, id: path.split("/").at(-1) } });
    if (path.includes("/proposals/")) return route.fulfill({ json: proposal });
    if (path.endsWith("/chat")) return route.fulfill({ json: { messages: [] } });
    throw new Error(`Unexpected API fixture: ${path}`);
  });
}

for (const order of ["history-last", "post-last"] as const) {
  test(`UI fixture: 历史与新回合双向合并且去重 ${order}`, async ({ page }) => {
    await fixtures(page); const history = gate(); const post = gate(); let posts = 0;
    const old = message("old", "已保存的历史回合"); const fresh = message("new", "本次完成的新回合");
    await page.route("**/api/publishing/chat*", async route => {
      if (route.request().method() === "GET") { await history.promise; return route.fulfill({ json: { messages: order === "post-last" ? [old, fresh] : [old] } }); }
      posts++; await post.promise; return route.fulfill({ json: { messages: [fresh], state_changed: false } });
    });
    await page.goto(`/publishing?manuscript=${MID}`);
    await page.getByRole("textbox", { name: "向出版助手发送消息" }).fill("只读网络夹具输入");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await expect.poll(() => posts).toBe(1);
    if (order === "history-last") { post.release(); await expect(page.getByText(fresh.content, { exact: true })).toBeVisible(); history.release(); }
    else { history.release(); await expect(page.getByText(old.content, { exact: true })).toBeVisible(); post.release(); }
    await expect(page.getByText(old.content, { exact: true })).toHaveCount(1);
    await expect(page.getByText(fresh.content, { exact: true })).toHaveCount(1);
    await expect(page.getByText("正在载入当前对话…", { exact: true })).toHaveCount(0);
    expect(posts).toBe(1);
  });
}

test("UI fixture: 账号入口保护未保存文件且只询问一次", async ({ page }) => {
  await fixtures(page); await page.goto(`/publishing?manuscript=${MID}`);
  const file = page.getByLabel("正文校样文件", { exact: true });
  await file.setInputFiles({ name: "unsaved-ui-fixture.txt", mimeType: "text/plain", buffer: Buffer.from("本地选择，不上传。") });
  let prompts = 0; let accept = false;
  page.on("dialog", async dialog => { prompts++; if (accept) await dialog.accept(); else await dialog.dismiss(); });
  await page.getByRole("link", { name: "账号与设置", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(MID));
  expect(prompts).toBe(1);
  expect(await file.evaluate(input => (input as HTMLInputElement).files?.length)).toBe(1);
  accept = true; await page.getByRole("link", { name: "账号与设置", exact: true }).click();
  await expect(page).toHaveURL(/\/$/); expect(prompts).toBe(2);
});

test("UI fixture: 审核重载单飞且拒绝后清除旧材料与勾选", async ({ page }) => {
  await fixtures(page); let calls = 0; const retry = gate();
  await page.route(`**/api/publishing/proposals/${PID}`, async route => {
    calls++; if (calls === 1) return route.fulfill({ status: 502, json: { detail: "合成首次网络故障" } });
    await retry.promise; return route.fulfill({ status: 403, json: { detail: "合成访问已撤销" } });
  });
  await page.goto(`/publishing/review/${PID}`);
  const button = page.getByRole("button", { name: "重新载入", exact: true });
  await expect(button).toBeVisible();
  // Two synchronous clicks model a rapid retry before React commits the loading render.
  await button.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
  await expect.poll(() => calls).toBeGreaterThan(1);
  await page.waitForTimeout(100); expect(calls).toBe(2);
  retry.release(); await expect(page.getByRole("alert").filter({ hasText: "合成访问已撤销" })).toBeVisible();
  await expect(page.locator('input[name="human_acknowledgment"]')).toHaveCount(0);
  await expect(page.getByText(`快照 SHA-256：${proposal.digest}`, { exact: false })).toHaveCount(0);
});

test("UI fixture: 历史失败只重试 GET，不重放已完成的新回合", async ({ page }) => {
  await fixtures(page); let gets = 0; let posts = 0;
  const old = message("saved-history", "失败恢复后的旧回合"); const fresh = message("saved-post", "已完成且不应重放的新回合");
  await page.route("**/api/publishing/chat*", route => {
    if (route.request().method() === "POST") { posts++; return route.fulfill({ json: { messages: [fresh], state_changed: false } }); }
    gets++; return gets === 1 ? route.fulfill({ status: 503, json: { detail: "合成历史服务暂不可用" } }) : route.fulfill({ json: { messages: [old, fresh] } });
  });
  await page.goto(`/publishing?manuscript=${MID}`);
  await expect(page.getByRole("alert").filter({ hasText: "合成历史服务暂不可用" })).toBeVisible();
  await page.getByRole("textbox", { name: "向出版助手发送消息" }).fill("历史失败时仍可发送");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.getByText(fresh.content, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "重新载入历史", exact: true }).click();
  await expect(page.getByText(old.content, { exact: true })).toHaveCount(1);
  await expect(page.getByText(fresh.content, { exact: true })).toHaveCount(1);
  await expect(page.getByText("正在载入当前对话…", { exact: true })).toHaveCount(0);
  expect(gets).toBe(2); expect(posts).toBe(1);
});

test("UI fixture: 切稿后旧 GET/POST 不进入新稿对话且保留未发送输入", async ({ page }) => {
  await fixtures(page); const oldHistory = gate(); const oldPost = gate(); let posts = 0;
  await page.route("**/api/publishing/chat*", async route => {
    if (route.request().method() === "POST") { posts++; await oldPost.promise; return route.fulfill({ json: { messages: [message("late-post", "前稿延迟新回合")], state_changed: false } }); }
    const mid = new URL(route.request().url()).searchParams.get("manuscript_id");
    if (mid === MID) { await oldHistory.promise; return route.fulfill({ json: { messages: [message("late-history", "前稿延迟历史")] } }); }
    return route.fulfill({ json: { messages: mid === OTHER ? [message("other-history", "当前稿件历史")] : [] } });
  });
  await page.goto(`/publishing?manuscript=${MID}`);
  const composer = page.getByRole("textbox", { name: "向出版助手发送消息" });
  await composer.fill("前稿待完成输入"); await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect.poll(() => posts).toBe(1);
  await page.getByRole("button", { name: /^我的工作/ }).click();
  await page.getByRole("link").filter({ hasText: "另一篇合成稿件" }).click();
  await expect(page).toHaveURL(new RegExp(OTHER));
  await expect(page.getByText("当前稿件历史", { exact: true })).toBeVisible();
  await composer.fill("切稿后尚未发送的输入");
  const historyDone = page.waitForResponse(response => response.request().method() === "GET" && response.url().includes(`/chat?manuscript_id=${MID}`));
  const postDone = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/chat"));
  oldHistory.release(); oldPost.release(); await Promise.all([historyDone, postDone]);
  await expect(page.getByRole("button", { name: "发送消息", exact: true })).toBeEnabled();
  await expect(page.getByText("前稿延迟历史", { exact: true })).toHaveCount(0);
  await expect(page.getByText("前稿延迟新回合", { exact: true })).toHaveCount(0);
  await expect(page.getByText("当前稿件历史", { exact: true })).toHaveCount(1);
  await expect(composer).toHaveValue("切稿后尚未发送的输入"); expect(posts).toBe(1);
});

test("UI fixture: 审核权限失败立即移除已勾选材料且恢复需要重新核对", async ({ page }) => {
  await fixtures(page); let confirmations = 0;
  await page.route(`**/api/publishing/proposals/${PID}/confirmations`, route => { confirmations++; return route.fulfill({ status: 403, json: { detail: "合成确认权限已撤销" } }); });
  await page.goto(`/publishing/review/${PID}`);
  const ack = page.locator('input[name="human_acknowledgment"]');
  await ack.check(); await page.getByRole("button", { name: "确认交作者校样", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "合成确认权限已撤销" })).toBeVisible();
  await expect(ack).toHaveCount(0);
  await page.getByRole("button", { name: "重新载入", exact: true }).click();
  await expect(ack).not.toBeChecked();
  await expect(page.getByRole("button", { name: "确认交作者校样", exact: true })).toBeDisabled();
  expect(confirmations).toBe(1);
});

test("UI fixture: 未保存保护保留新标签页与下载的默认行为", async ({ page }) => {
  await fixtures(page); await page.goto(`/publishing?manuscript=${MID}`);
  await page.getByLabel("正文校样文件", { exact: true }).setInputFiles({ name: "still-unsaved.txt", mimeType: "text/plain", buffer: Buffer.from("仅本地选择。") });
  let prompts = 0; page.on("dialog", async dialog => { prompts++; await dialog.dismiss(); });
  const popup = page.context().waitForEvent("page");
  await page.getByRole("link", { name: "账号与设置", exact: true }).click({ modifiers: ["Control"] });
  const opened = await popup; await expect(opened).toHaveURL(/\/$/); await opened.close();
  await expect(page).toHaveURL(new RegExp(MID)); expect(prompts).toBe(0);
  await page.evaluate(() => { const link = document.createElement("a"); link.href = "data:text/plain,synthetic"; link.download = "fixture.txt"; link.textContent = "合成下载夹具"; document.querySelector('main[aria-label="稿件材料"]')!.appendChild(link); });
  const download = page.waitForEvent("download"); await page.getByRole("link", { name: "合成下载夹具", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("fixture.txt"); expect(prompts).toBe(0);
  expect(await page.getByLabel("正文校样文件", { exact: true }).evaluate(input => (input as HTMLInputElement).files?.length)).toBe(1);
});

test("UI fixture: 最新历史授权拒绝屏蔽更早 pending POST 的迟到内容", async ({ page }) => {
  await fixtures(page); const history = gate(); const post = gate(); let posts = 0;
  await page.route("**/api/publishing/chat*", async route => {
    if (route.request().method() === "GET") { await history.promise; return route.fulfill({ status: 403, json: { detail: "合成最新材料授权已撤销" } }); }
    posts++; await post.promise; return route.fulfill({ json: { messages: [message("revoked-late-post", "撤权前已完成但迟到的私密回复")], state_changed: false } });
  });
  await page.goto(`/publishing?manuscript=${MID}`);
  const composer = page.getByRole("textbox", { name: "向出版助手发送消息" });
  await composer.fill("这次请求在撤权之前开始");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect.poll(() => posts).toBe(1);
  history.release(); await expect(page.getByRole("alert").filter({ hasText: "合成最新材料授权已撤销" })).toBeVisible();
  post.release(); await expect(composer).toHaveValue("");
  await expect(page.getByText("撤权前已完成但迟到的私密回复", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("alert").filter({ hasText: "合成最新材料授权已撤销" })).toBeVisible();
  await expect(page.getByText("正在载入当前对话…", { exact: true })).toHaveCount(0); expect(posts).toBe(1);
});

test("UI fixture: 最新 POST 授权拒绝后旧 GET 也不能恢复私密历史", async ({ page }) => {
  await fixtures(page); const history = gate(); let posts = 0;
  await page.route("**/api/publishing/chat*", async route => {
    if (route.request().method() === "GET") { await history.promise; return route.fulfill({ json: { messages: [message("revoked-late-history", "撤权之前生成的迟到历史")] } }); }
    posts++; return route.fulfill({ status: 403, json: { detail: "合成发送时权限已撤销" } });
  });
  await page.goto(`/publishing?manuscript=${MID}`);
  const composer = page.getByRole("textbox", { name: "向出版助手发送消息" });
  await composer.fill("应保留这条未完成输入"); await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "合成发送时权限已撤销" })).toBeVisible();
  const response = page.waitForResponse(result => result.request().method() === "GET" && result.url().includes("/chat?"));
  history.release(); await response;
  await expect(page.getByRole("button", { name: "重新载入历史", exact: true })).toBeEnabled();
  await expect(page.getByText("撤权之前生成的迟到历史", { exact: true })).toHaveCount(0);
  await expect(composer).toHaveValue("应保留这条未完成输入");
  await expect(page.getByText("正在载入当前对话…", { exact: true })).toHaveCount(0); expect(posts).toBe(1);
});

test("UI fixture: 同账号角色收窄后重新加载历史并隐藏旧角色回合", async ({ page }) => {
  await fixtures(page); let role = "production_editor"; let gets = 0; let posts = 0;
  await page.route("**/api/publishing/session", route => route.fulfill({ json: { ...session, user: { ...session.user, role } } }));
  await page.route(`**/api/publishing/manuscripts/${MID}`, route => route.fulfill({ json: role === "production_editor" ? detail : { ...detail, production: { ...detail.production, mode: "author", can_upload_proof: undefined, draft_file: undefined, accepted_materials: undefined } } }));
  await page.route("**/api/publishing/chat*", route => {
    if (route.request().method() === "POST") { posts++; role = "author"; return route.fulfill({ json: { messages: [message("producer-last", "旧制作角色最后回合")], state_changed: true } }); }
    gets++; return route.fulfill({ json: { messages: role === "production_editor" ? [message("producer-private", "旧制作角色保密历史")] : [message("author-safe", "当前作者角色安全历史")] } });
  });
  await page.goto(`/publishing?manuscript=${MID}`);
  await expect(page.getByText("旧制作角色保密历史", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "向出版助手发送消息" }).fill("合成权限刷新请求");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.getByText("作者", { exact: true })).toBeVisible();
  await expect(page.getByText("旧制作角色保密历史", { exact: true })).toHaveCount(0);
  await expect(page.getByText("旧制作角色最后回合", { exact: true })).toHaveCount(0);
  await expect(page.getByText("当前作者角色安全历史", { exact: true })).toHaveCount(1);
  expect(gets).toBe(2); expect(posts).toBe(1);
});
