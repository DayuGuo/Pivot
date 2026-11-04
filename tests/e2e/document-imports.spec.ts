import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { Citation, DocumentImport, DocumentSegment, Dossier, DossierData, Message, Session } from "../../apps/web/components/library/types";

const ID = "a0000000-0000-4000-8000-000000000015";
const BASE = "b0000000-0000-4000-8000-000000000015";
const NEXT = "b0000000-0000-4000-8000-000000000025";
const IMPORT = "c0000000-0000-4000-8000-000000000015";
const PDF = path.resolve("tests/documents/synthetic-manuscript.pdf");
const raw = readFileSync(PDF);
const sha = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");
const firstPage = "Title: Automatic Candidate Title\nAuthor: Synthetic Author Alpha\nAffiliation: Synthetic Research Institute\n🙂 A synthetic metadata fixture, not a real manuscript.";
const secondPage = "Methods\nThe sample includes 24 synthetic records and no control group.\nEND-OF-SYNTHETIC-DOCUMENT-TRACE-2026";
const text = firstPage + "\n\n" + secondPage;
const points = (value: string) => Array.from(value).length;
const offset = (value: string) => points(text.slice(0, text.indexOf(value)));
const segments: DocumentSegment[] = [
  { kind: "pdf_page", number: 1, start: 0, end: points(firstPage), text: firstPage },
  { kind: "pdf_page", number: 2, start: points(firstPage) + 2, end: points(text), text: secondPage },
];
const session: Session = { user: { id: "ui-synthetic-editor", name: "合成编辑", email: "editor@synthetic.test", role: "editor" }, journal: { id: "ui-synthetic-journal", name: "本地合成期刊" }, csrf_token: "ui-synthetic-csrf" };
const proposal: DossierData = { title: "Automatic Candidate Title", abstract: "This completely synthetic candidate validates import review, original text locations and human-only confirmation. No real confidential manuscript or person is included.", language: "en", keywords: ["synthetic"], authors: [{ name: "Synthetic Author Alpha", email: "alpha@synthetic.test", orcid: null, affiliations: ["Synthetic Research Institute"], corresponding: true, contributions: ["Synthetic methods"], source_note: "合成文件内作者字段，仅用于界面测试。" }], source_kind: "synthetic", source_note: "全部为合成界面测试资料，不包含保密信息。" };

type State = { confirmed: boolean; data: DossierData; confirmBodies: Record<string, unknown>[]; uploadBodies: Record<string, unknown>[]; messages: Message[] };
function document() { return { import_id: IMPORT, filename: "synthetic-manuscript.pdf", media_type: "application/pdf", sha256: sha(raw), byte_size: raw.length, download_url: `/api/dossiers/${ID}/imports/${IMPORT}/file`, parser: "synthetic-ui-contract", origin_digest: "f".repeat(64), segments, warnings: [], approval: { id: "synthetic-human-approval", by: session.user.id, at: "2026-11-03T15:00:00Z" } }; }
function snapshot(state: State, version = state.confirmed ? NEXT : BASE): Dossier {
  const next = version === NEXT;
  const body = next ? text : "原有的合成保存正文，尚未使用导入候选。";
  return { id: ID, revision: state.confirmed ? 3 : 2, version_id: version, version_no: next ? 3 : 2, content_digest: (next ? "d" : "a").repeat(64), is_current: version === (state.confirmed ? NEXT : BASE), verified: next, verification: next ? { id: "synthetic-check", by: session.user.id, at: "2026-11-03T15:00:00Z" } : null, data: next ? state.data : { ...structuredClone(proposal), title: "原有保存资料" }, file: { filename: next ? "synthetic-manuscript.pdf.extracted.txt" : "synthetic-base.txt", sha256: sha(body), byte_size: Buffer.byteLength(body), media_type: "text/plain", text: body, download_url: `/api/dossiers/${ID}/versions/${version}/file` }, missing: [], versions: [...(state.confirmed ? [{ id: NEXT, number: 3, title: state.data.title, created_at: "2026-11-03T15:00:00Z", verified: true }] : []), { id: BASE, number: 2, title: "原有保存资料", created_at: "2026-11-03T14:00:00Z", verified: false }], messages: state.messages, model: { provider: "mock", model: "ui-contract", ready: true }, document: next ? document() : null };
}
function imported(state: State): DocumentImport {
  const title = "Automatic Candidate Title";
  return { id: IMPORT, dossier_id: ID, base_revision: 2, base_version_id: BASE, digest: "e".repeat(64), filename: "synthetic-manuscript.pdf", media_type: "application/pdf", byte_size: raw.length, sha256: sha(raw), original_download_url: `/api/dossiers/${ID}/imports/${IMPORT}/file`, parser: "synthetic-ui-contract", text, segments, warnings: [], proposed_data: structuredClone(proposal), field_sources: [{ field_path: "title", value: title, quote: title, start: offset(title), end: offset(title) + points(title), kind: "pdf_page", number: 1 }], metadata_provider: "mock", metadata_model: "labelled-frontmatter-v1", telemetry: [], confirmed_version_id: state.confirmed ? NEXT : null, editable: !state.confirmed };
}
function citation(state: State, metadata = false): Citation {
  const quote = metadata ? "Alpha" : "The sample includes 24 synthetic records and no control group.";
  const sourceQuote = metadata ? proposal.authors[0].name : quote;
  const sourceStart = offset(sourceQuote), sourceEnd = sourceStart + points(sourceQuote);
  return { source_id: metadata ? "META" : "BODY", kind: metadata ? "metadata" : "text", quote, source_text: metadata ? proposal.authors[0].name : secondPage, label: metadata ? "作者 1 · 姓名" : "完整正文", version_id: NEXT, version_no: 3, content_digest: snapshot(state, NEXT).content_digest, file_sha256: metadata ? null : sha(text), start: metadata ? points(proposal.authors[0].name.slice(0, proposal.authors[0].name.indexOf(quote))) : sourceStart, end: metadata ? points(proposal.authors[0].name) : sourceEnd, line_start: metadata ? null : 8, line_end: metadata ? null : 8, field_path: metadata ? "authors.0.name" : null, document: { origin_digest: document().origin_digest, sha256: sha(raw), filename: document().filename, media_type: "application/pdf", download_url: document().download_url, locations: [{ kind: "pdf_page", number: metadata ? 1 : 2, start: sourceStart, end: sourceEnd }], ...(metadata ? { source_start: sourceStart, source_end: sourceEnd, source_quote: sourceQuote } : {}) } };
}
async function fixtures(page: Page, options: { confirmed?: boolean; confirmStatus?: number; abortFirstConfirm?: boolean; badOrigin?: boolean } = {}) {
  const state: State = { confirmed: options.confirmed ?? false, data: structuredClone(proposal), confirmBodies: [], uploadBodies: [], messages: [] };
  await page.route("**/api/publishing/session", route => route.fulfill({ json: session }));
  await page.route("**/api/dossiers", route => route.fulfill({ json: { items: [{ id: ID, title: snapshot(state).data.title, revision: state.confirmed ? 3 : 2, version_id: state.confirmed ? NEXT : BASE, version_no: state.confirmed ? 3 : 2, verified: state.confirmed, updated_at: "2026-11-03T15:00:00Z" }] } }));
  await page.route(`**/api/dossiers/${ID}`, route => route.fulfill({ json: snapshot(state) }));
  await page.route(`**/api/dossiers/${ID}/versions/*`, route => route.fulfill({ json: snapshot(state, new URL(route.request().url()).pathname.split("/").at(-1)) }));
  await page.route(`**/api/dossiers/${ID}/imports`, async route => {
    if (route.request().method() === "POST") { state.uploadBodies.push(route.request().postDataJSON()); await route.fulfill({ json: { import_id: IMPORT, dossier_id: ID } }); }
    else await route.fulfill({ json: { items: [{ id: IMPORT, filename: "synthetic-manuscript.pdf", created_at: "2026-11-03T15:00:00Z", confirmed_version_id: state.confirmed ? NEXT : null, base_revision: 2 }] } });
  });
  await page.route(`**/api/dossiers/${ID}/imports/${IMPORT}`, route => route.fulfill({ json: imported(state) }));
  await page.route(`**/api/dossiers/${ID}/imports/${IMPORT}/confirm`, async route => {
    const body = route.request().postDataJSON(); state.confirmBodies.push(body);
    if (options.confirmStatus) { await route.fulfill({ status: options.confirmStatus, json: { detail: options.confirmStatus === 403 ? "无权访问此资料" : "模型服务暂不可用，请重试。" } }); return; }
    state.data = body.data; state.confirmed = true;
    if (options.abortFirstConfirm && state.confirmBodies.length === 1) { await route.abort("connectionfailed"); return; }
    await route.fulfill({ json: { dossier_id: ID, version_id: NEXT } });
  });
  await page.route(`**/api/dossiers/${ID}/chat`, async route => {
    const refs = [citation(state), citation(state, true)];
    if (options.badOrigin) refs[0].document!.origin_digest = "x".repeat(64);
    const response: Message = { id: "synthetic-grounded-turn", question: route.request().postDataJSON().message, answer: "Mock 模拟来源定位", provider: "mock", version_id: NEXT, version_no: 3, claims: [{ text: "合成样本没有设置对照组。", citations: [refs[0]] }, { text: "作者姓名由合成原稿提取，未经身份认证。", citations: [refs[1]] }] };
    state.messages = [response]; await route.fulfill({ json: response });
  });
  return state;
}
async function openReview(page: Page) { await page.goto(`/library/imports/${IMPORT}?dossier=${ID}`); await expect(page.getByRole("heading", { name: "导入核对", exact: true })).toBeVisible(); }
const acknowledge = (page: Page) => page.locator('input[name="import-acknowledged"]');

test("导入 UI：真实上传字节、候选来源核对和人类确认才创建新版本", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto(`/library?dossier=${ID}`);
  await page.getByRole("button", { name: "导入 PDF / Word", exact: true }).click();
  await page.getByLabel("PDF 或 Word 稿件", { exact: true }).setInputFiles(PDF);
  const upload = page.getByRole("button", { name: "提取并打开核对表单", exact: true });
  await expect(upload).toBeDisabled();
  await page.getByRole("checkbox", { name: /我确认文件为合成/ }).check(); await upload.click();
  await expect(page).toHaveURL(new RegExp(`/library/imports/${IMPORT}`));
  expect(state.uploadBodies).toHaveLength(1); expect(state.uploadBodies[0].authorized_material).toBe(true);
  const file = state.uploadBodies[0].file as { filename: string; content_base64: string }; expect(file.filename).toBe("synthetic-manuscript.pdf"); expect(Buffer.from(file.content_base64, "base64")).toEqual(raw);
  expect(state.confirmed).toBe(false); await expect(page.getByText(/当前仍为 v2/)).toBeVisible();
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue(proposal.title);
  await page.screenshot({ path: test.info().outputPath("import-review-desktop.png") });
  const confirm = page.getByRole("button", { name: "核对并保存为新版本", exact: true }); await expect(confirm).toBeDisabled(); await expect(acknowledge(page)).not.toBeChecked();
  await page.getByRole("tab", { name: "识别依据", exact: true }).click(); await page.getByRole("button", { name: "题名 · PDF 第 1 页", exact: true }).click(); await expect(page.locator('mark[aria-label="已定位提取依据"]')).toHaveText(proposal.title);
  await page.getByRole("tab", { name: "核对表单", exact: true }).click(); await acknowledge(page).check(); await expect(confirm).toBeEnabled();
  await page.getByLabel("题名", { exact: true }).fill("负责人核对后合成题名"); await expect(acknowledge(page)).not.toBeChecked(); await expect(confirm).toBeDisabled();
  await acknowledge(page).check(); await confirm.click(); await expect(page).toHaveURL(new RegExp(`/library\\?dossier=${ID}$`));
  expect(state.confirmBodies).toHaveLength(1); expect(state.confirmBodies[0].acknowledged).toBe(true); expect(state.confirmBodies[0].digest).toBe("e".repeat(64)); expect((state.confirmBodies[0].data as DossierData).title).toBe("负责人核对后合成题名");
  await expect(page.getByLabel("题名", { exact: true })).toHaveValue("负责人核对后合成题名"); await expect(page.getByRole("region", { name: "资料内容", exact: true }).getByText("v3 · 已核对", { exact: true })).toBeVisible();
  await page.getByLabel("询问当前资料").fill("请定位原稿方法与作者资料"); await page.getByRole("button", { name: "发送", exact: true }).click();
  await page.getByRole("button", { name: "定位原文：完整正文，v3", exact: true }).click(); await expect(page.locator('mark[aria-label="已定位引用原文"]')).toHaveText(citation(state).quote); await expect(page.getByText(/synthetic-manuscript.pdf · PDF 第 2 页/)).toBeVisible(); await expect(page.getByRole("link", { name: "下载原稿", exact: true })).toHaveAttribute("href", document().download_url); expect(await page.locator("iframe").count()).toBe(0);
  await page.getByRole("button", { name: "返回当前资料", exact: true }).click(); await page.getByRole("button", { name: "定位原文：作者 1 · 姓名，v3", exact: true }).click(); await expect(page.locator('mark[aria-label="已定位引用原文"]')).toHaveText("Alpha"); await expect(page.getByText(/synthetic-manuscript.pdf · PDF 第 1 页/)).toBeVisible();
  await page.reload(); await expect(page.getByText("合成样本没有设置对照组。", { exact: true })).toBeVisible();
});

test("导入 UI：同UUID恢复已提交但丢失响应的确认", async ({ page }) => {
  const state = await fixtures(page, { abortFirstConfirm: true }); await openReview(page);
  await acknowledge(page).check(); await page.getByRole("button", { name: "核对并保存为新版本", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible(); await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试原请求", exact: true }).click(); await expect(page).toHaveURL(new RegExp(`/library\\?dossier=${ID}$`));
  expect(state.confirmBodies).toHaveLength(2); expect(state.confirmBodies[0]).toEqual(state.confirmBodies[1]); await expect(page.getByRole("region", { name: "资料内容", exact: true }).getByText("v3 · 已核对", { exact: true })).toBeVisible();
});

test("导入 UI：失败后编辑字段取消旧重试，撤权清除候选全文", async ({ page }) => {
  const state = await fixtures(page, { confirmStatus: 500 }); await openReview(page); await acknowledge(page).check(); await page.getByRole("button", { name: "核对并保存为新版本", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toBeVisible(); await expect(acknowledge(page)).not.toBeChecked(); await page.getByLabel("题名", { exact: true }).fill("失败后更新的人类题名"); await expect(page.getByRole("button", { name: "重试原请求", exact: true })).toHaveCount(0); expect(state.confirmed).toBe(false);
  await page.route(`**/api/dossiers/${ID}/imports/${IMPORT}/confirm`, route => route.fulfill({ status: 403, json: { detail: "无权访问此资料" } }));
  await acknowledge(page).check(); await page.getByRole("button", { name: "核对并保存为新版本", exact: true }).click(); await expect(page.getByRole("link", { name: "返回登录", exact: true })).toBeVisible(); await expect(page.getByText(proposal.title, { exact: true })).toHaveCount(0); await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
});

test("导入 UI：待核对记录可恢复，旧doc拒绝，窄屏保留对话", async ({ page }) => {
  await fixtures(page); await page.goto(`/library?dossier=${ID}`); await page.getByRole("tab", { name: "版本", exact: true }).click(); await page.getByText("导入记录", { exact: true }).click(); await page.getByRole("link", { name: /synthetic-manuscript.pdf/ }).click(); await expect(page).toHaveURL(new RegExp(`/library/imports/${IMPORT}`));
  await page.setViewportSize({ width: 375, height: 812 }); await expect(page.getByLabel("询问当前资料")).toBeVisible(); await expect(page.getByRole("tab", { name: "核对表单", exact: true })).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false); await page.screenshot({ path: test.info().outputPath("document-import-mobile.png") });
  await page.getByRole("link", { name: "返回当前资料", exact: true }).click(); await page.getByRole("button", { name: "导入 PDF / Word", exact: true }).click(); await page.getByLabel("PDF 或 Word 稿件", { exact: true }).setInputFiles({ name: "legacy.doc", mimeType: "application/msword", buffer: Buffer.from("synthetic unsupported legacy") }); await expect(page.getByText(/请先将旧版 .doc 另存为 .docx/)).toBeVisible(); await expect(page.getByRole("button", { name: "提取并打开核对表单", exact: true })).toBeDisabled();
});

test("导入 UI：原件摘要或位置不匹配时拒绝引用定位", async ({ page }) => {
  await fixtures(page, { confirmed: true, badOrigin: true }); await page.goto(`/library?dossier=${ID}`); await page.getByLabel("询问当前资料").fill("核对合成原文"); await page.getByRole("button", { name: "发送", exact: true }).click(); await page.getByRole("button", { name: "定位原文：完整正文，v3", exact: true }).click(); await expect(page.getByText(/引用与原版内容不匹配/)).toBeVisible(); await expect(page.locator("mark")).toHaveCount(0);
});

for (const extension of ["pdf", "docx"] as const) {
  test(`文档真实 API：${extension}提取候选→人工核对→新版本→原件引用`, async ({ page }) => {
    test.setTimeout(90000);
    const health = await page.request.get("/api/health"); expect((await health.json()).editorial_model.provider).toBe("mock");
    await page.goto("/"); await page.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test"); await page.getByLabel("密码", { exact: true }).fill("EditorDemo2026!"); await page.getByRole("button", { name: "进入工作台", exact: true }).click(); await expect(page.getByRole("button", { name: "内部审阅资料", exact: true })).toBeVisible();
    const auth = await (await page.request.get("/api/publishing/session")).json();
    const created = await page.request.post("/api/dossiers", { headers: { "X-CSRF-Token": auth.csrf_token }, data: { request_id: crypto.randomUUID(), title: `合成${extension}导入 ${Date.now()}`, source_kind: "synthetic", source_note: "完全合成的本地文档验收资料，不包含保密信息。", authorized_material: true } }); expect(created.status()).toBe(200); const { dossier_id: id } = await created.json();
    await page.goto(`/library?dossier=${id}`); await page.getByRole("button", { name: "导入 PDF / Word", exact: true }).click();
    await page.getByLabel("PDF 或 Word 稿件", { exact: true }).setInputFiles(path.resolve(`tests/documents/synthetic-manuscript.${extension}`)); await page.getByRole("checkbox", { name: /我确认文件为合成/ }).check();
    const pending = page.waitForResponse(response => response.url().endsWith(`/api/dossiers/${id}/imports`) && response.request().method() === "POST"); await page.getByRole("button", { name: "提取并打开核对表单", exact: true }).click(); const result = await pending; expect(result.status()).toBe(200); const { import_id: importId } = await result.json();
    await expect(page).toHaveURL(new RegExp(`/library/imports/${importId}`)); const original = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier; expect(original.version_no).toBe(1); expect(original.file).toBeNull(); expect(original.verified).toBe(false);
    const candidate = await (await page.request.get(`/api/dossiers/${id}/imports/${importId}`)).json() as DocumentImport; expect(candidate.text).toContain("END-OF-SYNTHETIC-DOCUMENT-TRACE-2026"); expect(candidate.proposed_data.authors.map(author => author.name)).toEqual(["Synthetic Author Alpha", "Synthetic Author Beta"]); expect(candidate.metadata_provider).toBe("mock");
    await expect(page.getByLabel("题名", { exact: true })).toHaveValue("Synthetic Editorial Review Manuscript"); await expect(acknowledge(page)).not.toBeChecked(); await expect(page.getByRole("button", { name: "核对并保存为新版本", exact: true })).toBeDisabled();
    await page.getByRole("tab", { name: "提取全文", exact: true }).click(); await expect(page.getByText(/END-OF-SYNTHETIC-DOCUMENT-TRACE-2026/)).toBeVisible(); const download = await page.request.get(candidate.original_download_url); expect(download.status()).toBe(200); expect(await download.body()).toEqual(readFileSync(path.resolve(`tests/documents/synthetic-manuscript.${extension}`)));
    await page.getByRole("tab", { name: "核对表单", exact: true }).click(); const reviewedTitle = `负责人核对${extension}稿件 ${Date.now()}`; await page.getByLabel("题名", { exact: true }).fill(reviewedTitle); await acknowledge(page).check(); await page.getByRole("button", { name: "核对并保存为新版本", exact: true }).click(); await expect(page).toHaveURL(new RegExp(`/library\\?dossier=${id}$`));
    const saved = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier; expect(saved.version_no).toBe(2); expect(saved.verified).toBe(true); expect(saved.data.title).toBe(reviewedTitle); expect(saved.file?.text).toContain("END-OF-SYNTHETIC-DOCUMENT-TRACE-2026"); expect(saved.document?.sha256).toBe(candidate.sha256); expect(saved.document?.filename).toBe(`synthetic-manuscript.${extension}`);
    await page.getByLabel("询问当前资料").fill("定位合成作者和原文依据"); await page.getByRole("button", { name: "发送", exact: true }).click(); await page.getByRole("button", { name: /定位原文：/ }).first().click(); await expect(page.locator('mark[aria-label="已定位引用原文"]')).toBeVisible(); await expect(page.getByRole("link", { name: "下载原稿", exact: true })).toHaveAttribute("href", saved.document!.download_url); await expect(page.getByText(extension === "pdf" ? /PDF 第 \d+ 页/ : /Word 第 \d+ 段/)).toBeVisible();
    await page.reload(); await expect(page.getByLabel("题名", { exact: true })).toHaveValue(reviewedTitle); expect((await (await page.request.get(`/api/dossiers/${id}`)).json()).verified).toBe(true);
  });
}

test("作者关联：不确定线索可定位，换序不改原候选标签，重复ORCID不能确认", async ({ page }) => {
  const state = await fixtures(page);
  const uncertain = imported(state);
  uncertain.proposed_data.authors[0].orcid = "0000-0002-1825-0097";
  uncertain.proposed_data.authors.push({ ...structuredClone(uncertain.proposed_data.authors[0]), name: "Synthetic Author Beta", email: "beta@synthetic.test", corresponding: false });
  uncertain.metadata_uncertainties = [{ field_path: "authors.0.email", reason: "author_link_unresolved", evidence: { start: 0, end: points(firstPage), quote: firstPage, kind: "pdf_page", number: 1 } }];
  await page.route(`**/api/dossiers/${ID}/imports/${IMPORT}`, route => route.fulfill({ json: uncertain }));
  await openReview(page);
  await page.getByRole("button", { name: "上移作者 2", exact: true }).click();
  await page.getByText("1 项原稿关联需要核对", { exact: true }).click();
  await expect(page.getByText(/原候选作者 1（Synthetic Author Alpha）/)).toBeVisible();
  await expect(page.getByLabel("作者关联提示")).toContainText("同一 ORCID 被填写给多位作者");
  await acknowledge(page).check();
  await page.getByRole("button", { name: "核对并保存为新版本", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "同一 ORCID 不能用于多位作者" })).toBeVisible();
  await expect(page.locator('input[name="author-0-orcid"]')).toBeFocused();
  expect(state.confirmBodies).toHaveLength(0);
  await page.getByRole("tab", { name: "识别依据", exact: true }).click();
  await page.getByRole("button", { name: "查看原文线索", exact: true }).click();
  await expect(page.locator('mark[aria-label="已定位提取依据"]')).toHaveText(firstPage);
  await expect(acknowledge(page)).not.toBeChecked();
  await page.screenshot({ path: "artifacts/spec020/association-desktop.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByLabel("询问当前资料")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.screenshot({ path: "artifacts/spec020/association-mobile.png" });
});
