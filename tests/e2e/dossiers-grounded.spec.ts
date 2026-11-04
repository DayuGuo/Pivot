import { test, expect, type Page } from "@playwright/test";
import type { Citation, Dossier, Message, Session } from "../../apps/web/components/library/types";

const ID = "10000000-0000-4000-8000-000000000014";
const OTHER = "10000000-0000-4000-8000-000000000024";
const OLD = "20000000-0000-4000-8000-000000000014";
const CURRENT = "20000000-0000-4000-8000-000000000024";
const oldText = "# 合成历史全文\n🙂 开头。确切方法：随机分组，样本为合成数据。\n全文末尾，仅供本地界面测试。";
const quote = "确切方法：随机分组，样本为合成数据。";
const currentText = "# 合成当前全文\n本版改为合成观察研究，全文与历史版不同。\n正文结尾。";
const session: Session = { user: { id: "synthetic-editor", name: "合成编辑", email: "editor@example.test", role: "editor" }, journal: { id: "synthetic-journal", name: "合成期刊" }, csrf_token: "synthetic-csrf" };

function snapshot(version = CURRENT, id = ID): Dossier {
  const old = version === OLD;
  return {
    id, revision: 2, version_id: version, version_no: old ? 1 : 2, content_digest: (old ? "a" : "b").repeat(64), is_current: !old, verified: false, verification: null,
    data: { title: id === OTHER ? "另一份合成资料" : old ? "合成历史资料" : "合成当前资料", abstract: "完整合成摘要，仅供本地界面测试，不含真实保密稿件或个人数据。", language: "zh", keywords: ["合成"], authors: [{ name: old ? "历史作者甲😀" : "当前作者乙", email: "synthetic@example.test", orcid: null, corresponding: true, affiliations: ["合成机构"], contributions: [], source_note: "本地合成元数据" }], source_kind: "synthetic", source_note: "全部内容为授权本地合成资料。" },
    file: { filename: old ? "old-synthetic.md" : "current-synthetic.md", sha256: (old ? "1" : "2").repeat(64), byte_size: Buffer.byteLength(old ? oldText : currentText), media_type: "text/markdown", text: old ? oldText : currentText, download_url: `/api/dossiers/${id}/versions/${version}/file` }, missing: [],
    versions: [{ id: CURRENT, number: 2, title: "合成当前资料", created_at: "2026-11-03T10:00:00Z", verified: false }, { id: OLD, number: 1, title: "合成历史资料", created_at: "2026-11-03T09:00:00Z", verified: false }],
    messages: [], model: { provider: "deepseek", model: "deepseek-flash", ready: true },
  };
}
function citation(kind: "text" | "metadata" = "text"): Citation {
  const text = kind === "text" ? oldText : "历史作者甲😀";
  const selected = kind === "text" ? quote : "作者甲😀";
  const start = Array.from(text.slice(0, text.indexOf(selected))).length;
  return { source_id: kind === "text" ? "T0" : "M1", kind, quote: selected, source_text: text, label: kind === "text" ? "合成方法原文" : "第一作者姓名", version_id: OLD, version_no: 1, content_digest: "a".repeat(64), file_sha256: kind === "text" ? "1".repeat(64) : null, start, end: start + Array.from(selected).length, line_start: kind === "text" ? 2 : null, line_end: kind === "text" ? 2 : null, field_path: kind === "metadata" ? "authors.0.name" : null };
}
function answer(): Message {
  return { id: "grounded-old", question: "历史版方法与作者是什么？", answer: "不应与结构化结论重复展示的服务端纯文本。", provider: "deepseek", model: "deepseek-flash", version_id: OLD, version_no: 1, questions: ["这份合成资料的预先分析计划是否已提供？"], claims: [{ text: "历史版本在方法描述中使用随机分组。", citations: [citation()] }, { text: "录入的第一作者为历史作者甲，身份仍未认证。", citations: [citation("metadata")] }], external_references: [{ status: "verified_metadata", doi: "10.1371/journal.pmed.0020124", title: "Why Most Published Research Findings Are False", authors: ["John P. A. Ioannidis"], year: 2005, url: "https://untrusted.invalid/arbitrary", source_url: "https://untrusted.invalid/metadata", retrieved_at: "2026-11-03T10:00:00Z", scope: "bibliographic_metadata_only" }], coverage: { total_chunks: 10, read_chunks: 2, total_characters: 2000, read_characters: 240, complete: false } };
}
async function fixtures(page: Page, modify?: (detail: Dossier) => void) {
  await page.route("**/api/publishing/session", route => route.fulfill({ json: session }));
  await page.route("**/api/dossiers", route => route.fulfill({ json: { items: [{ id: ID, title: "合成当前资料", revision: 2, version_id: CURRENT, version_no: 2, verified: false, updated_at: "2026-11-03T10:00:00Z" }, { id: OTHER, title: "另一份合成资料", revision: 2, version_id: CURRENT, version_no: 2, verified: false, updated_at: "2026-11-03T10:00:00Z" }] } }));
  await page.route(`**/api/dossiers/${ID}`, route => { const detail = snapshot(); detail.messages = [answer()]; modify?.(detail); return route.fulfill({ json: detail }); });
  await page.route(`**/api/dossiers/${OTHER}`, route => route.fulfill({ json: snapshot(CURRENT, OTHER) }));
  await page.route(`**/api/dossiers/${ID}/versions/${OLD}`, route => route.fulfill({ json: snapshot(OLD) }));
}

test("资料证据 UI：逐字定位历史全文和作者字段，保留当前未保存表单", async ({ page }) => {
  await fixtures(page);
  await page.goto(`/library?dossier=${ID}`);
  await expect(page.getByText("DeepSeek · 只读审阅 · 结论待人工复核", { exact: true })).toBeVisible();
  await expect(page.getByText(/部分覆盖，不能据此排除其他内容/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "待确认", exact: true })).toBeVisible();
  await expect(page.getByText("这份合成资料的预先分析计划是否已提供？", { exact: true })).toBeVisible();
  await expect(page.getByText("不应与结构化结论重复展示的服务端纯文本。", { exact: true })).toHaveCount(0);
  await page.getByLabel("题名", { exact: true }).fill("未保存的当前题名");
  await page.getByRole("button", { name: "定位原文：合成方法原文，v1", exact: true }).click();
  await expect(page.locator("mark")).toHaveText(quote);
  await expect(page.locator("mark")).toBeFocused();
  await expect(page.getByText("历史版本的证据；当前资料与未保存编辑保持不变。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回当前资料", exact: true }).click();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("未保存的当前题名");
  await page.getByRole("button", { name: "定位原文：第一作者姓名，v1", exact: true }).click();
  await expect(page.locator("mark")).toHaveText("作者甲😀");
  await expect(page.getByText(/录入资料，不代表作者或 ORCID 身份已认证/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Why Most Published Research Findings Are False", exact: true })).toHaveAttribute("href", "https://doi.org/10.1371/journal.pmed.0020124");
  await expect(page.getByRole("link", { name: "Crossref 记录", exact: true })).toHaveAttribute("href", "https://api.crossref.org/works/10.1371/journal.pmed.0020124");
  await expect(page.locator('a[href*="untrusted.invalid"]')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("grounded-desktop.png") });
});

test("资料证据 UI：不匹配的版本哈希拒绝定位，撤权清除材料与历史", async ({ page }) => {
  await fixtures(page);
  await page.route(`**/api/dossiers/${ID}/versions/${OLD}`, route => route.fulfill({ json: { ...snapshot(OLD), content_digest: "c".repeat(64) } }));
  await page.goto(`/library?dossier=${ID}`);
  await page.getByRole("button", { name: "定位原文：合成方法原文，v1", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "引用与原版内容不匹配" })).toBeVisible();
  await expect(page.locator("mark")).toHaveCount(0);
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("合成当前资料");
  await page.route(`**/api/dossiers/${ID}/versions/${OLD}`, route => route.fulfill({ status: 404, json: { detail: "合成资料访问已撤销" } }));
  await page.getByRole("button", { name: "定位原文：合成方法原文，v1", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "合成资料访问已撤销" })).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await expect(page.getByText("历史版本在方法描述中使用随机分组。", { exact: true })).toHaveCount(0);
});

test("资料证据 UI：旧引用迟到不会覆盖新资料", async ({ page }) => {
  await fixtures(page); let release!: () => void; let started = false; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/dossiers/${ID}/versions/${OLD}`, async route => { started = true; await gate; return route.fulfill({ json: snapshot(OLD) }); });
  try {
    await page.goto(`/library?dossier=${ID}`);
    await page.getByRole("button", { name: "定位原文：合成方法原文，v1", exact: true }).click();
    await expect.poll(() => started).toBe(true);
    await page.getByRole("link", { name: /另一份合成资料/ }).click();
    await expect(page.getByLabel("题名", { exact: true })).toHaveValue("另一份合成资料");
    release();
    await expect(page.locator("mark")).toHaveCount(0);
    await expect(page.getByText("历史版本在方法描述中使用随机分组。", { exact: true })).toHaveCount(0);
  } finally { release?.(); }
});

test("资料证据 UI：模型网络失败保留问题并用同 UUID 重试", async ({ page }) => {
  await fixtures(page, detail => { detail.model = { provider: "mock", model: "mock-dossier-review", ready: true }; });
  const requests: { request_id: string; version_id: string }[] = [];
  await page.route(`**/api/dossiers/${ID}/chat`, route => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) return route.abort();
    return route.fulfill({ json: { ...answer(), id: "mock-retry", question: "请继续核对方法", answer: "本轮模拟回复，仅验证重试。", provider: "mock", claims: [] } });
  });
  await page.goto(`/library?dossier=${ID}`);
  await page.getByLabel("询问当前资料").fill("请继续核对方法"); await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试原请求", exact: true }).click();
  await expect(page.getByText("本轮模拟回复，仅验证重试。", { exact: true })).toBeVisible();
  await expect(page.getByText("v1 · 历史版本 · Mock · 模拟结果", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2); expect(requests[1].request_id).toBe(requests[0].request_id); expect(requests[1].version_id).toBe(CURRENT);
});

test("资料证据 UI：窄屏与键盘可以读取和返回引用", async ({ page }) => {
  await fixtures(page); await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/library?dossier=${ID}`);
  const source = page.getByRole("button", { name: "定位原文：合成方法原文，v1", exact: true });
  await source.focus(); await page.keyboard.press("Enter");
  await expect(page.locator("mark")).toHaveText(quote);
  await expect(page.locator("mark")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("grounded-mobile.png") });
  await page.getByRole("button", { name: "返回当前资料", exact: true }).click();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("合成当前资料");
  await expect(source).toBeFocused();
  await expect(page.getByLabel("询问当前资料")).toBeVisible();
});

test("资料证据真实 API：Mock 回复持久化并能定位本版全文", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test"); await page.getByLabel("密码", { exact: true }).fill("EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(page.getByRole("button", { name: "内部审阅资料", exact: true })).toBeVisible();
  const state = await (await page.request.get("/api/publishing/session")).json();
  const headers = { "X-CSRF-Token": state.csrf_token };
  const response = await page.request.post("/api/dossiers", { headers, data: { request_id: crypto.randomUUID(), title: `合成证据UI ${Date.now()}`, source_kind: "synthetic", source_note: "所有资料均为本地合成并已授权用于自动验收。", authorized_material: true } });
  expect(response.status()).toBe(200); const id = (await response.json()).dossier_id;
  const sourceText = "# 合成全文\n研究方法：使用合成随机分组，样本均为虚构资料，仅检验引用定位。\n这不是实际科研结论。";
  const saved = await page.request.post(`/api/dossiers/${id}/versions`, { headers, data: { request_id: crypto.randomUUID(), expected_revision: 1, data: { ...snapshot().data, title: "合成证据自动验收" }, file: { filename: "synthetic-grounded.md", content_base64: Buffer.from(sourceText).toString("base64") } } });
  expect(saved.status()).toBe(200);
  await page.goto(`/library?dossier=${id}`);
  await expect(page.getByText("Mock · 模拟审阅 · 结论待人工复核", { exact: true })).toBeVisible();
  await page.getByLabel("询问当前资料").fill("请根据全文说明研究方法，逐条引用原文。"); await page.getByRole("button", { name: "发送", exact: true }).click();
  const citationButton = page.getByRole("button", { name: /^定位原文：/ }).first(); await expect(citationButton).toBeVisible();
  await citationButton.click(); await expect(page.locator("mark")).not.toBeEmpty();
  await page.reload(); await expect(page.getByRole("button", { name: /^定位原文：/ }).first()).toBeVisible();
  const persisted = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  expect(persisted.messages.at(-1)?.provider).toBe("mock"); expect(persisted.messages.at(-1)?.claims?.[0].citations.length).toBeGreaterThan(0); expect(persisted.verified).toBe(false);
});

test("原文支持：未通过的候选不作为结论展示，但依据仍可核对", async ({ page }) => {
  await fixtures(page);
  const candidate = { ...answer().claims![0], text: "未采纳的夸大结论", support: { status: "contradicted" as const, method: "ai_context_check", reason: "contradiction" } };
  await page.route(`**/api/dossiers/${ID}`, route => route.fulfill({ json: { ...snapshot(), messages: [{ ...answer(), claims: [], answer: "本轮没有保留可采纳的结论。", withheld_claims: [candidate], support_review: { schema: "claim-support.v1", method: "ai_context_check", evaluated_claims: 1, withheld_count: 1 } }] } }));
  await page.goto(`/library?dossier=${ID}`);
  await expect(page.getByText("未采纳的夸大结论", { exact: true })).toBeHidden();
  await expect(page.getByText("原文支持检查（AI）：0 条保留，1 条待核对；仍须人工复核。", { exact: true })).toBeVisible();
  await page.getByLabel("题名", { exact: true }).fill("保留当前未保存输入");
  await page.getByText("1 条候选结论未通过支持检查", { exact: true }).click();
  await expect(page.getByText("未采纳的夸大结论", { exact: true })).toBeVisible();
  await expect(page.getByText("与原文矛盾：结论与引文上下文矛盾。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "定位待核对依据：合成方法原文，v1", exact: true }).click();
  await expect(page.locator("mark")).toHaveText(quote);
  await page.getByRole("button", { name: "返回当前资料", exact: true }).click();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("保留当前未保存输入");
});

test("原文支持：旧回答不被补成已经通过的语义检查", async ({ page }) => {
  await fixtures(page); await page.goto(`/library?dossier=${ID}`);
  await expect(page.getByText("此历史回答尚未做语义支持检查，引用仍可定位，请人工复核结论。", { exact: true })).toBeVisible();
  await expect(page.getByText(/原文支持检查（AI）/)).toHaveCount(0);
});

test("人工复核：不完整回执同UUID恢复、改内容重勾、刷新保留历史", async ({ page }) => {
  await fixtures(page);
  const writes: Record<string, unknown>[] = [], records: Record<string, unknown>[] = [];
  let reads = 0;
  await page.route(`**/api/dossiers/${ID}/answers/grounded-old/claims/claims/0/reviews`, async route => {
    if (route.request().method() === "GET") { ++reads; return route.fulfill({ json: { items: records, latest_id: records[0]?.id ?? null, next_cursor: null, claim_digest: "c".repeat(64), content_digest: "a".repeat(64) } }); }
    const data = route.request().postDataJSON(); writes.push(data);
    if (!records.length) records.push({ ...data, id: "30000000-0000-4000-8000-000000000014", review_no: 1, created_at: "2026-11-04T12:00:00Z" });
    return route.fulfill({ json: writes.length === 1 ? {} : records[0] });
  });
  await page.goto(`/library?dossier=${ID}`);
  await expect(page.getByRole("heading", { name: "合成当前资料", exact: true })).toBeVisible();
  expect(reads).toBe(0);
  const feedback = page.getByRole("region", { name: "结论人工复核", exact: true }).first();
  await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
  await feedback.getByLabel("核对理由", { exact: true }).fill("原文只描述合成记录，不能支持临床疗效。");
  await feedback.getByRole("checkbox").check();
  await feedback.getByLabel("复核意见", { exact: true }).selectOption("unsupported");
  await expect(feedback.getByRole("checkbox")).not.toBeChecked();
  await feedback.getByRole("checkbox").check();
  await feedback.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await expect(feedback.getByRole("alert")).toContainText("未完整收到保存回执");
  await feedback.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await expect(feedback.getByRole("status")).toHaveText("人工复核已保存。");
  expect(writes).toHaveLength(2); expect(writes[0].request_id).toBe(writes[1].request_id); expect(records).toHaveLength(1);
  await page.reload();
  await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
  await expect(feedback.getByText("最近人工复核：无依据 · 第 1 次", { exact: true })).toBeVisible();
  await feedback.getByText("复核记录（1）", { exact: true }).click();
  await expect(feedback.getByText("原文只描述合成记录，不能支持临床疗效。", { exact: true })).toBeVisible();
  await page.screenshot({ path: "artifacts/spec021/human-feedback-desktop.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByLabel("询问当前资料")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.screenshot({ path: "artifacts/spec021/human-feedback-mobile.png" });
});

test("人工复核：撤权清除材料和表单，不提交旧登录身份", async ({ page }) => {
  await fixtures(page);
  let posts = 0;
  await page.route(`**/api/dossiers/${ID}/answers/grounded-old/claims/claims/0/reviews`, route => { if (route.request().method() === "POST") ++posts; return route.fulfill({ json: { items: [], latest_id: null, next_cursor: null, claim_digest: "c".repeat(64), content_digest: "a".repeat(64) } }); });
  await page.goto(`/library?dossier=${ID}`);
  const feedback = page.getByRole("region", { name: "结论人工复核", exact: true }).first();
  await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
  await feedback.getByLabel("核对理由", { exact: true }).fill("已查看原文，准备记录复核意见。");
  await feedback.getByRole("checkbox").check();
  await page.route("**/api/publishing/session", route => route.fulfill({ json: { ...session, user: { ...session.user, id: "another-editor" } } }));
  await feedback.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "访问权限或身份已变化" })).toContainText("访问权限或身份已变化");
  await expect(page.getByText("已查看原文，准备记录复核意见。", { exact: true })).toHaveCount(0);
  expect(posts).toBe(0);
});

test("人工复核：翻旧记录不采用并发变化的新前置ID", async ({ page }) => {
  await fixtures(page);
  const previous = "30000000-0000-4000-8000-000000000014", concurrent = "30000000-0000-4000-8000-000000000024";
  const posts: Record<string, unknown>[] = [];
  const record = { id: previous, verdict: "supported", note: "初始负责人已核对原文。", review_no: 2, created_at: "2026-11-04T12:00:00Z", claim_digest: "c".repeat(64), content_digest: "a".repeat(64) };
  await page.route(`**/api/dossiers/${ID}/answers/grounded-old/claims/claims/0/reviews*`, route => {
    if (route.request().method() === "POST") { posts.push(route.request().postDataJSON()); return route.fulfill({ status: 409, json: { detail: "已有新的人工复核，请重新载入后核对" } }); }
    const older = new URL(route.request().url()).searchParams.has("before");
    return route.fulfill({ json: { items: [{ ...record, id: older ? "30000000-0000-4000-8000-000000000034" : previous, review_no: older ? 1 : 2 }], latest_id: older ? concurrent : previous, next_cursor: older ? null : 2, claim_digest: "c".repeat(64), content_digest: "a".repeat(64) } });
  });
  await page.goto(`/library?dossier=${ID}`);
  const feedback = page.getByRole("region", { name: "结论人工复核", exact: true }).first();
  await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
  await feedback.getByLabel("核对理由", { exact: true }).fill("本次新增核对理由，但不能覆盖尚未看到的新意见。");
  await feedback.getByRole("checkbox").check();
  await feedback.getByText("复核记录（1）", { exact: true }).click();
  await feedback.getByRole("button", { name: "更早复核", exact: true }).click();
  await expect(feedback.getByText("复核记录（2）", { exact: true })).toBeVisible();
  await feedback.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await expect(feedback.getByRole("alert")).toContainText("已有新的人工复核");
  expect(posts[0].expected_review_id).toBe(previous);
});
