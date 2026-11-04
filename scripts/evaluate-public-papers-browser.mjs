// Explicitly simulate the demo responsible editor on licensed public material.
// The model never receives a confirmation tool. No mail or editorial decision is made.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

assert(process.argv.includes("--live"), "Explicit --live required; this driver submits review forms and calls the live model.");
const stagingArg = process.argv.indexOf("--staging");
const stagingPath = stagingArg >= 0 ? process.argv[stagingArg + 1] : "artifacts/public-papers/staging.json";
const staged = JSON.parse(await readFile(resolve(stagingPath), "utf8"));
const manifest = JSON.parse(await readFile(resolve("evals/public_documents/manifest.json"), "utf8"));
const qaOnly = process.argv.includes("--qa-only");
const onlyIndex = process.argv.indexOf("--only-cases");
const onlyCases = onlyIndex >= 0 ? process.argv[onlyIndex + 1].split(",") : null;
const tagIndex = process.argv.indexOf("--question-tag");
const questionTag = tagIndex >= 0 ? process.argv[tagIndex + 1] : "";
const origin = "http://127.0.0.1:3100";
const reportIndex = process.argv.indexOf("--report");
const output = resolve(reportIndex >= 0 ? process.argv[reportIndex + 1] : "artifacts/public-papers/browser-review-qa.json");
const outputDir = dirname(output);
const report = process.argv.includes("--resume") ? JSON.parse(await readFile(output, "utf8")) : { passed: false, human_review_simulated_by_test_driver: true, model_confirmation_tools: 0, confirm_posts: 0, mail_or_decision_requests: 0, page_errors: 0, cases: [] };
report.passed = false;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(15000);
page.on("pageerror", () => report.page_errors++);
page.on("request", request => {
  if (request.method() === "POST" && /\/imports\/[^/]+\/confirm$/.test(new URL(request.url()).pathname)) report.confirm_posts++;
  if (request.method() !== "GET" && /\/email|\/decisions|\/publish|\/withdraw/.test(new URL(request.url()).pathname)) report.mail_or_decision_requests++;
});
const questions = {
  clinical: [
    "只根据当前原件的 Results，说明找到了多少份 CPG、多少条 guideline statements，并给出逐字原文引用；不要提供诊疗建议。",
    "请核对 Alastair O’Brien 和 Jeffrey Leung 分别属于哪个 Division，不要把 Medicine 与 Surgery 混淆。请引用作者机构原文或对应作者字段。",
  ],
  reproducible: [
    "根据 Rule 7 原文，说明为什么不能仅保存图像，还需要保存什么。给出相关正文的逐字引用。",
    "Anton Nekrutenko 和 James Taylor 分别来自哪所大学？请给出各自机构的原文或作者字段引用，不要混配。",
  ],
  "research-findings": [
    "仅根据原件 Summary，研究主张为真的概率受哪些因素影响？只说 study power 和 bias 这两项，并逐字引用，不要扩展为诊疗建议。",
    "John P. A. Ioannidis 的作者机构中，希腊和美国分别是哪所大学？请给出对应原文或作者机构字段的引用，不要使用参考文献作者的信息。",
  ],
};
async function json(path) {
  const response = await page.request.get(origin + path);
  assert.equal(response.status(), 200);
  return response.json();
}
function paperFor(caseId) { return manifest.papers.find(paper => paper.files.some(file => file.case === caseId)); }
try {
  assert.equal((await json("/api/health")).editorial_model.provider, "deepseek");
  await page.goto(origin);
  await page.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test");
  await page.getByLabel("密码", { exact: true }).fill("EditorDemo2026!");
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(page.getByRole("button", { name: "内部审阅资料", exact: true })).toBeVisible();
  for (const stagedCase of staged.cases.filter(item => !onlyCases || onlyCases.includes(item.case))) {
    assert.equal(stagedCase.http_status, 200);
    const paper = paperFor(stagedCase.case), gold = paper.review_data;
    const did = stagedCase.dossier_id, iid = stagedCase.import_id;
    let result = report.cases.find(item => item.case === stagedCase.case);
    if (!result) { result = { case: stagedCase.case, passed: false, queries: [] }; report.cases.push(result); }
    const original = await json(`/api/dossiers/${did}`);
    if (!original.verified) {
    await page.goto(`${origin}/library/imports/${iid}?dossier=${did}`);
    const acknowledged = page.locator('input[name="import-acknowledged"]');
    await expect(acknowledged).not.toBeChecked();
    const confirm = page.getByRole("button", { name: "核对并保存为新版本", exact: true });
    await expect(confirm).toBeDisabled();
    await expect(page.getByLabel("询问当前资料")).toBeVisible();
    // Gold values were checked against full source bylines/JATS; not model output.
    await page.locator('input[name="title"]').fill(gold.title);
    await page.locator('textarea[name="abstract"]').fill(gold.abstract);
    await page.locator('input[name="keywords"]').fill(gold.keywords.join(", "));
    await page.locator('select[name="language"]').selectOption(gold.language);
    assert.equal(await page.locator('input[name$="-name"]').count(), gold.authors.length);
    for (const [index, author] of gold.authors.entries()) {
      await page.locator(`input[name="author-${index}-name"]`).fill(author.name);
      await page.locator(`input[name="author-${index}-email"]`).fill(author.email);
      await page.locator(`textarea[name="author-${index}-affiliations"]`).fill(author.affiliations.join("\n"));
      await page.locator(`textarea[name="author-${index}-contributions"]`).fill("");
      await page.locator(`input[name="author-${index}-orcid"]`).fill(author.orcid || "");
      await page.locator(`textarea[name="author-${index}-source"]`).fill(author.source_note);
      if (author.corresponding) await page.locator('input[name="corresponding-author"]').nth(index).check();
    }
    await page.locator('textarea[name="source-note"]').fill(gold.source_note);
    await acknowledged.check();
    await expect(confirm).toBeEnabled();
    // Any field edit invalidates the prior declaration.
    await page.locator('input[name="title"]').fill(gold.title + " ");
    await expect(acknowledged).not.toBeChecked();
    await acknowledged.check();
    await page.screenshot({ path: resolve(outputDir, `${stagedCase.case}-review.png`) });
    const savedResponse = page.waitForResponse(response => response.url().endsWith(`/imports/${iid}/confirm`) && response.request().method() === "POST");
    await confirm.click();
    assert.equal((await savedResponse).status(), 200);
    await expect(page).toHaveURL(`${origin}/library?dossier=${did}`);
    }
    const saved = await json(`/api/dossiers/${did}`);
    assert.equal(saved.version_no, original.verified ? original.version_no : original.version_no + 1);
    assert.equal(saved.verified, true);
    assert.deepEqual(saved.data, gold);
    result.version_id = saved.version_id;
    result.form_review_and_new_version = true;
    await page.goto(`${origin}/library?dossier=${did}`);
    const file = paper.files.find(file => file.case === stagedCase.case);
    assert.equal(saved.document.sha256, file.sha256);
    const currentQuestions = questions[paper.id].map(message => qaOnly ? questionTag + "仅回答当前这一题，不复述历史问题。" + message : message);
    const expectedNewAnswers = currentQuestions.filter(message => !saved.messages.some(turn => turn.question === message && turn.provider === "deepseek" && turn.support_review?.method === "ai_context_check")).length;
    for (const [questionNo, message] of currentQuestions.entries()) {
      let answer = saved.messages.find(turn => turn.question === message && turn.provider === "deepseek" && turn.support_review?.method === "ai_context_check");
      let status = 200;
      if (!answer) {
        const pending = page.waitForResponse(response => response.url().endsWith(`/dossiers/${did}/chat`) && response.request().method() === "POST", { timeout: 80000 });
        await page.getByLabel("询问当前资料").fill(message);
        await page.getByRole("button", { name: "发送", exact: true }).click();
        const response = await pending;
        status = response.status();
        answer = await response.json();
      }
      const query = { question: message, status, passed: false };
      result.queries[questionNo] = query;
      assert.equal(status, 200);
      assert.equal(answer.provider, "deepseek");
      assert(answer.claims.length > 0);
      const citations = answer.claims.flatMap(claim => claim.citations);
      assert(citations.length > 0);
      for (const citation of citations) {
        assert.equal(citation.version_id, saved.version_id);
        assert.equal(citation.content_digest, saved.content_digest);
        const metadataValue = citation.field_path?.split(".").reduce((value, key) => value?.[key], saved.data);
        const raw = citation.kind === "text" ? saved.file.text : String(metadataValue);
        assert.equal(Array.from(raw).slice(citation.start, citation.end).join(""), citation.quote);
        if (citation.document) {
          assert.equal(citation.document.sha256, saved.document.sha256);
          assert.equal(citation.document.origin_digest, saved.document.origin_digest);
          assert(citation.document.locations.length > 0);
        }
      }
      assert.equal(answer.support_review?.method, "ai_context_check");
      assert(answer.claims.every(claim => claim.support?.status === "supported"));
      query.support_review = answer.support_review;
      query.withheld_claims = answer.withheld_claims ?? [];
      query.claims = answer.claims;
      query.coverage = answer.coverage;
      query.telemetry = answer.telemetry;
      const chosen = citations.find(citation => citation.kind === "text" && citation.document) || citations[0];
      const questionMessage = page.locator("article").filter({ hasText: message }).last();
      await expect(questionMessage).toBeVisible();
      // Match citation ordinal among identical labels in this exact question.
      const identical = citations.filter(citation => citation.label === chosen.label && citation.version_no === chosen.version_no);
      const ordinal = identical.indexOf(chosen);
      await questionMessage.getByRole("button", { name: `定位原文：${chosen.label}，v${chosen.version_no}`, exact: true }).nth(ordinal).click();
      const highlighted = page.locator('mark[aria-label="已定位引用原文"]');
      await expect(highlighted).toBeVisible();
      assert.equal(await highlighted.textContent(), chosen.quote);
      if (chosen.document) await expect(page.getByRole("link", { name: "下载原稿", exact: true })).toBeVisible();
      query.exact_browser_highlight = true;
      query.passed = true;
      await page.screenshot({ path: resolve(outputDir, `${stagedCase.case}-citation-${questionNo}.png`) });
      await page.getByRole("button", { name: "返回当前资料", exact: true }).click();
      await writeFile(output, JSON.stringify(report, null, 2));
    }
    await page.reload();
    await expect(page.getByRole("heading", { name: gold.title, exact: true, level: 2 })).toBeVisible();
    await expect(page.getByText("正在载入资料…", { exact: true })).toHaveCount(0);
    const refreshed = await json(`/api/dossiers/${did}`);
    assert.equal(refreshed.version_id, saved.version_id);
    assert.deepEqual(refreshed.data, gold);
    assert.equal(refreshed.messages.length, saved.messages.length + expectedNewAnswers);
    result.refresh_preserved = true;
    result.passed = true;
    await writeFile(output, JSON.stringify(report, null, 2));
    console.log("PASS", stagedCase.case, "review form, real DeepSeek, original citations and refresh");
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByLabel("询问当前资料")).toBeVisible();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: resolve(outputDir, "mobile.png") });
  assert.equal(report.confirm_posts, qaOnly ? 0 : 6);
  assert.equal(report.mail_or_decision_requests, 0);
  assert.equal(report.page_errors, 0);
  report.passed = true;
} finally {
  await writeFile(output, JSON.stringify(report, null, 2));
  await browser.close();
}
