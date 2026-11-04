// Explicit local-only acceptance: public licensed dossiers, simulated responsible editor.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
assert(process.argv.includes("--public-fixtures"), "Explicit public evaluation fixture consent required");
const staged = JSON.parse(await readFile("artifacts/spec020/staging.json", "utf8"));
const corpus = JSON.parse(await readFile("evals/public_documents/manifest.json", "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const base = "http://127.0.0.1:3100";
const report = { passed: false, responsible_editor_simulated_by_test_driver: true, cases: [], model_calls: 0, mail_or_decision_requests: 0, dossier_confirmations: 0, page_errors: 0 };
page.on("pageerror", () => ++report.page_errors);
page.on("request", request => { if (request.method() !== "POST") return; const url = new URL(request.url()).pathname; if (url.endsWith("/chat")) ++report.model_calls; if (url.endsWith("/confirm")) ++report.dossier_confirmations; if (/mail|decision/.test(url)) ++report.mail_or_decision_requests; });
async function json(path) { const response = await page.request.get(base + path); assert.equal(response.status(), 200); return response.json(); }
try {
  await page.goto(base);
  await page.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test");
  await page.getByLabel("密码", { exact: true }).fill("EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(page.getByRole("button", { name: "内部审阅资料", exact: true })).toBeVisible();
  for (const spec of [
    { file: "research-findings-word", prefix: "仅根据原件 Summary", index: 0, verdict: "unsupported", note: "自动验收模拟负责人：此条将录入摘要称为原件Summary；所附元数据引用未关联原文件，不能支持该来源断言。" },
    { file: "clinical-word", prefix: "请核对 Alastair", index: 2, verdict: "uncertain", note: "自动验收模拟负责人：复合结论还包含上标及联系方式字段一致性，当前引文未直接呈现全部关联，暂待进一步核对。" },
  ]) {
    const entry = staged.cases.find(c => c.case === spec.file); assert(entry);
    const did = entry.dossier_id, before = await json(`/api/dossiers/${did}`);
    const expectedFile = corpus.papers.flatMap(p => p.files).find(f => f.case === spec.file);
    assert.equal(before.data.source_kind, "public_authorized"); assert.equal(before.document?.sha256, expectedFile.sha256);
    const message = before.messages.find(m => m.question.startsWith(spec.prefix)); assert(message && message.claims[spec.index]);
    const claim = message.claims[spec.index], cite = claim.citations[0];
    await page.goto(`${base}/library?dossier=${did}`);
    const article = page.locator("article").filter({ has: page.getByText(message.question, { exact: true }) });
    await expect(article).toBeVisible();
    const block = article.getByText(claim.text, { exact: true }).locator("..");
    await block.getByRole("button", { name: `定位原文：${cite.label}，v${cite.version_no}`, exact: true }).first().click();
    await expect(page.locator('mark[aria-label="已定位引用原文"]')).toHaveText(cite.quote);
    const feedback = block.getByRole("region", { name: "结论人工复核", exact: true });
    await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
    const path = `/api/dossiers/${did}/answers/${message.id}/claims/claims/${spec.index}/reviews`;
    let history = await json(path);
    if (history.items.length) assert(history.items[0].note === spec.note && history.items[0].verdict === spec.verdict, "Existing responsible feedback differs; automated overwrite refused");
    if (!history.items.length) {
      await feedback.getByLabel("复核意见", { exact: true }).selectOption(spec.verdict);
      await feedback.getByLabel("核对理由", { exact: true }).fill(spec.note);
      await feedback.getByRole("checkbox").check();
      await feedback.getByRole("button", { name: "保存人工复核", exact: true }).click();
      await expect(feedback.getByRole("status")).toHaveText("人工复核已保存。");
    }
    history = await json(path); assert.equal(history.items[0].verdict, spec.verdict);
    assert.deepEqual(await json(`/api/dossiers/${did}`), before);
    const summary = await json(`/api/dossiers/${did}/answers/${message.id}/review-summary`);
    const downloadEvent = page.waitForEvent("download");
    await article.getByRole("link", { name: "下载复核摘要", exact: true }).click();
    const downloaded = await downloadEvent;
    assert.deepEqual(JSON.parse(await readFile(await downloaded.path(), "utf8")), summary);
    assert.equal(summary.metrics.reviewed_claims, 1);
    assert.equal(summary.metrics.model_adopted_human_unsupported, spec.verdict === "unsupported" ? 1 : 0);
    assert.equal(summary.metrics.human_uncertain, spec.verdict === "uncertain" ? 1 : 0);
    await page.reload();
    await feedback.getByRole("button", { name: "人工复核", exact: true }).click();
    await feedback.getByText(/复核记录（/).click();
    await expect(feedback.getByText(spec.note, { exact: true })).toBeVisible();
    await page.screenshot({ path: `artifacts/spec021/${spec.file}-feedback.png` });
    report.cases.push({ file: spec.file, original_answer_and_version_unchanged: true, exact_source_highlight: true, summary_download_exact: true, refresh_preserved: true, verdict: spec.verdict, metrics: summary.metrics });
  }
  assert.equal(report.model_calls, 0); assert.equal(report.mail_or_decision_requests, 0); assert.equal(report.dossier_confirmations, 0); assert.equal(report.page_errors, 0);
  report.passed = true;
} finally { await writeFile("artifacts/spec021/public-feedback.json", JSON.stringify(report, null, 2)); await browser.close(); }
