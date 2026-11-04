// Actual prebuilt private UI; reads only the isolated acceptance test's credentials.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { chromium, expect } from "@playwright/test";
const reportPath = process.argv[2] || "artifacts/vps-preview-acceptance.json";
const accepted = JSON.parse(await readFile(reportPath, "utf8"));
assert(accepted.passed);
const config = JSON.parse(await readFile(`${accepted.state}/credentials.json`, "utf8"));
assert(config.project.startsWith("pivot-check-"));
const origin = `http://127.0.0.1:${config.port}`;
const result = { passed: false, page_errors: 0, confirmations: 0, mail_or_decisions: 0, cases: [] };
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
page.on("pageerror", () => result.page_errors++);
page.on("request", request => {
  if (request.method() === "GET") return;
  if (/\/confirm$/.test(new URL(request.url()).pathname)) result.confirmations++;
  if (/\/email|\/decisions|\/publish|\/withdraw/.test(new URL(request.url()).pathname)) result.mail_or_decisions++;
});
try {
  await page.goto(origin);
  await expect(page.getByLabel("邮箱", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("密码", { exact: true })).toHaveValue("");
  await expect(page.getByText("本地演示账号", { exact: true })).toHaveCount(0);
  await page.getByLabel("邮箱", { exact: true }).fill(config.email);
  await page.getByLabel("密码", { exact: true }).fill(config.password);
  await page.getByRole("button", { name: "进入工作台", exact: true }).click();
  await expect(page.getByRole("button", { name: "内部审阅资料", exact: true })).toBeVisible();
  for (const item of accepted.cases) {
    await page.goto(`${origin}/library?dossier=${item.dossier_id}`);
    await expect(page.getByLabel("询问当前资料")).toBeVisible();
    const response = await page.request.get(`${origin}/api/dossiers/${item.dossier_id}`);
    assert.equal(response.status(), 200);
    const snapshot = await response.json();
    assert(snapshot.verified);
    const last = snapshot.messages.at(-1);
    const citation = last.claims.flatMap(claim => claim.citations).find(c => c.kind === "text");
    await page.getByRole("button", { name: `定位原文：${citation.label}，v${citation.version_no}`, exact: true }).first().click();
    const mark = page.locator('mark[aria-label="已定位引用原文"]');
    await expect(mark).toBeVisible();
    assert.equal(await mark.textContent(), citation.quote);
    await expect(page.getByRole("link", { name: "下载原稿", exact: true })).toBeVisible();
    await page.screenshot({ path: `artifacts/vps-${accepted.provider}-${item.format}-citation.png` });
    await page.reload();
    const refreshed = await page.request.get(`${origin}/api/dossiers/${item.dossier_id}`);
    assert.deepEqual(await refreshed.json(), snapshot);
    result.cases.push({ format: item.format, exact_citation_highlight: true, refresh_preserved: true });
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByLabel("询问当前资料")).toBeVisible();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: `artifacts/vps-${accepted.provider}-mobile.png` });
  assert.equal(result.page_errors, 0);
  assert.equal(result.confirmations, 0);
  assert.equal(result.mail_or_decisions, 0);
  result.passed = true;
} finally {
  await writeFile(`artifacts/vps-${accepted.provider}-browser.json`, JSON.stringify(result, null, 2));
  await browser.close();
}
console.log(JSON.stringify(result));
