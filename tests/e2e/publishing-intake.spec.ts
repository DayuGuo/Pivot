import { test, expect, type Page } from "@playwright/test";

test("作者通过常驻对话创建真实投稿，核对资料后独立确认，编辑获得预审待办", async ({ page, browser }) => {
  test.setTimeout(90000);
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill("author@publishing.test");
  await page.getByLabel("密码", { exact: true }).fill("AuthorDemo2026!");
  await page.getByRole("button", { name: "进入工作台" }).click();
  await page.getByRole("button", { name: "出版工作台", exact: true }).click();
  const composer = page.getByRole("textbox", { name: "向出版助手发送消息" });
  await composer.fill("请创建一篇新投稿");
  const createdReply = page.waitForResponse(response => response.url().endsWith("/api/publishing/chat") && response.request().method() === "POST");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  const created = await (await createdReply).json();
  const createdId = created.messages[1].action.manuscript_id;
  await page.locator(`a[href="/publishing?manuscript=${createdId}"]`).filter({ hasText: "查看稿件" }).click();
  await expect(page.getByLabel("标题", { exact: true })).toBeVisible();
  const mid = new URL(page.url()).searchParams.get("manuscript")!;
  await composer.fill("请整理资料\n标题：合成开放科学浏览器验收\n摘要：本研究采用完全合成的测试材料验证投稿流程，覆盖资料整理、版本文件、负责人确认与编辑待办，并验证刷新后的持久化一致性。\n关键词：合成数据，出版流程");
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(page.getByText("模拟结果：已将识别到的信息整理为候选", { exact: false })).toBeVisible();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("合成开放科学浏览器验收");
  await page.reload();
  await expect(page.getByText("模拟结果：已将识别到的信息整理为候选", { exact: false })).toBeVisible();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("合成开放科学浏览器验收");
  await page.getByLabel("我确认稿件为原创", { exact: false }).check();
  await page.getByLabel("我确认拥有投稿所需的版权或授权", { exact: false }).check();
  await page.getByLabel("利益冲突", { exact: true }).selectOption("none");
  await page.getByLabel("伦理审批适用性", { exact: true }).selectOption("not_applicable");
  await page.getByRole("button", { name: "保存资料", exact: true }).click();
  await expect(page.getByText("资料已保存。", { exact: true })).toBeVisible();
  for (const [purpose, name] of [["manuscript", "synthetic-full.txt"], ["blinded_manuscript", "synthetic-anonymous.txt"]]) {
    await page.getByLabel("文件用途", { exact: true }).selectOption(purpose);
    await page.getByLabel("选择文件", { exact: true }).setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from("完全合成的无身份研究材料。\n不包含真实稿件内容。", "utf8") });
    await page.getByRole("button", { name: "上传并保存", exact: true }).click();
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "准备投稿审核", exact: true }).click();
  await page.getByRole("link", { name: "打开完整资料并由负责人确认", exact: true }).click();
  await expect(page.getByRole("heading", { name: "负责人审核", exact: true })).toBeVisible();
  await expect(composer).toBeVisible();
  const confirm = page.getByRole("button", { name: "确认并提交投稿", exact: true });
  await expect(confirm).toBeDisabled();
  await page.getByRole("checkbox", { name: "我已核对完整资料", exact: false }).check();
  await confirm.click();
  await expect(page.getByText("此操作已由负责人确认，结果已保存。", { exact: false })).toBeVisible();
  await page.getByRole("link", { name: "返回稿件", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveCount(0);
  await expect(page.getByText("材料完整性预审", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText("合成开放科学浏览器验收", { exact: true }).first()).toBeVisible();
  const editor = await browser.newContext(); const editorPage = await editor.newPage();
  await editorPage.goto("/");
  await editorPage.getByLabel("邮箱", { exact: true }).fill("editor@publishing.test");
  await editorPage.getByLabel("密码", { exact: true }).fill("EditorDemo2026!");
  await editorPage.getByRole("button", { name: "进入工作台" }).click();
  await expect(editorPage.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
  await editorPage.goto(`/publishing?manuscript=${mid}`);
  await expect(editorPage.locator(`a[href="/publishing?manuscript=${mid}"]`).filter({ hasText: "材料完整性预审" }).filter({ hasText: "合成开放科学浏览器验收" })).toBeVisible();
  await expect(editorPage.getByRole("textbox", { name: "向出版助手发送消息" })).toBeVisible();
  const staffComposer = editorPage.getByRole("textbox", { name: "向出版助手发送消息" });
  await staffComposer.fill("请整理检查意见，备注：这是合成测试，请负责人逐项核对当前版本材料。");
  await editorPage.getByRole("button", { name: "发送消息", exact: true }).click();
  await expect(editorPage.getByRole("button", { name: "采用检查意见候选", exact: true })).toBeVisible();
  await editorPage.getByRole("button", { name: "采用检查意见候选", exact: true }).click();
  await expect(editorPage.getByLabel("检查结果", { exact: true })).toHaveValue("");
  await expect(editorPage.getByRole("checkbox", { name: "我已人工检查当前版本的稿件材料", exact: true })).not.toBeChecked();
  await passCheck(editorPage, "材料完整性预审");
  await expect(editorPage.getByRole("heading", { name: "相似度报告人工复核", exact: true })).toBeVisible();
  await editorPage.getByLabel("查重报告文件", { exact: true }).setInputFiles({ name: "synthetic-report.txt", mimeType: "text/plain", buffer: Buffer.from("合成人工复核报告；未执行任何外部查重服务。", "utf8") });
  await editorPage.getByRole("button", { name: "上传并保存报告", exact: true }).click();
  await expect(editorPage.getByRole("link", { name: "synthetic-report.txt", exact: true })).toBeVisible();
  await passCheck(editorPage, "相似度报告人工复核", "我已人工阅读并复核本次上传的查重报告");
  await passCheck(editorPage, "匿名材料筛选", "我已人工检查供审稿人使用的匿名稿件");
  const chief = await browser.newContext(); const chiefPage = await chief.newPage();
  await chiefPage.goto("/");
  await chiefPage.getByLabel("邮箱", { exact: true }).fill("chief@publishing.test");
  await chiefPage.getByLabel("密码", { exact: true }).fill("ChiefDemo2026!");
  await chiefPage.getByRole("button", { name: "进入工作台" }).click();
  await expect(chiefPage.getByRole("button", { name: "出版工作台", exact: true })).toBeVisible();
  await chiefPage.goto(`/publishing?manuscript=${mid}`);
  await passCheck(chiefPage, "主编范围初筛", "我确认稿件符合本刊受稿范围");
  const selector = chiefPage.getByLabel("责任编辑", { exact: true });
  const selectedEditor = await selector.locator("option").filter({ hasText: "editor@publishing.test" }).getAttribute("value");
  expect(selectedEditor).toBeTruthy();
  await selector.selectOption(selectedEditor!);
  await chiefPage.getByLabel("分派说明", { exact: true }).fill("为合成测试稿件分派本刊责任编辑。");
  await chiefPage.getByRole("button", { name: "准备编辑分派审核", exact: true }).click();
  await chiefPage.getByRole("link", { name: "打开完整资料并由负责人确认", exact: true }).click();
  await approve(chiefPage, "确认并分派责任编辑");
  await editorPage.reload();
  await passCheck(editorPage, "责任编辑质量评估", "我确认稿件质量适合送交同行评审");
  await expect(editorPage.getByText("寻找审稿人", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText("寻找审稿人", { exact: true }).first()).toBeVisible();
  await editor.close(); await chief.close();
});

async function approve(page: Page, label: string) {
  const confirm = page.getByRole("button", { name: label, exact: true });
  await expect(confirm).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "向出版助手发送消息" })).toBeVisible();
  await page.getByRole("checkbox", { name: "我已核对完整资料", exact: false }).check();
  await confirm.click();
  await expect(page.getByText("此操作已由负责人确认，结果已保存。", { exact: false })).toBeVisible();
  await page.getByRole("link", { name: "返回稿件", exact: true }).click();
}

async function passCheck(page: Page, stage: string, extra?: string) {
  await expect(page.getByRole("heading", { name: stage, exact: true })).toBeVisible();
  await page.getByLabel("检查结果", { exact: true }).selectOption("pass");
  await page.getByLabel("人工检查意见", { exact: true }).fill(`负责人已阅读本次合成稿件材料，完成${stage}。`);
  await page.getByRole("checkbox", { name: "我已人工检查当前版本的稿件材料", exact: true }).check();
  if (extra) await page.getByRole("checkbox", { name: extra, exact: true }).check();
  await page.getByRole("button", { name: "准备检查审核", exact: true }).click();
  await page.getByRole("link", { name: "打开完整资料并由负责人确认", exact: true }).click();
  await approve(page, `确认通过${stage}`);
}

