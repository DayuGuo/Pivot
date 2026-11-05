import { expect, test, type Page } from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import type { Dossier, Session } from "../../apps/web/components/library/types";
import type { RevisionPacket } from "../../apps/web/components/library/revision-types";

const original = "合成研究 😀\n方法：样本量为10，采用随机分组。\n结果：仅用于合成回归。";
const revised = "合成研究 😀\n方法：样本量改为20，采用随机分组，并说明纳入标准。\n结果：仅用于合成回归。";
const reply = "意见1：请报告样本量。回复：已将样本量改为20，见修订稿方法段。";

async function prepare(page: Page) {
  const login = await page.request.post("/api/auth/login", { data: { email: "editor@publishing.test", password: "EditorDemo2026!" } });
  expect(login.status()).toBe(200);
  const session = await login.json() as Session;
  const headers = { "X-CSRF-Token": session.csrf_token };
  const creation = await page.request.post("/api/dossiers", { headers, data: { request_id: randomUUID(), title: `合成修回核对 ${randomUUID()}`, source_kind: "synthetic", source_note: "独立浏览器自动回归生成的完全合成材料，不代表真实投稿。", authorized_material: true } });
  expect(creation.status()).toBe(200);
  const { dossier_id: id } = await creation.json();
  let current = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
  async function save(text: string) {
    const response = await page.request.post(`/api/dossiers/${id}/versions`, { headers, data: { request_id: randomUUID(), expected_revision: current.revision, data: current.data, file: { filename: "same-synthetic-name.txt", content_base64: Buffer.from(text).toString("base64") } } });
    expect(response.status()).toBe(200);
    current = await (await page.request.get(`/api/dossiers/${id}`)).json() as Dossier;
    return current;
  }
  const base = await save(original), currentRevision = await save(revised);
  const checkBody = { request_id: randomUUID(), expected_revision: currentRevision.revision, base_version_id: base.version_id, revised_version_id: currentRevision.version_id, requirements: [{ text: "请报告研究样本量。", original_context: "审稿意见1：请报告研究样本量，并解释抽样范围。" }], response_text: reply, source_note: "全部为自动测试合成材料；仅模拟编辑资料核对，不代签或作出版决定。", base_complete: false, revised_complete: false, requirements_complete: false, response_complete: false, authorized_material: true };
  async function createPacket() {
    const response = await page.request.post(`/api/dossiers/${id}/revision-checks`, { headers, data: checkBody });
    expect(response.status()).toBe(200);
    const { check_id } = await response.json();
    const packet = await (await page.request.get(`/api/dossiers/${id}/revision-checks/${check_id}`)).json() as RevisionPacket;
    return packet;
  }
  return { id, base, current: currentRevision, headers, checkBody, createPacket, save };
}

async function fillCheck(page: Page, baseVersion: string) {
  await page.getByRole("combobox", { name: "原稿版本", exact: true }).selectOption(baseVersion);
  await page.getByLabel("核对要求 1", { exact: true }).fill("请报告研究样本量。");
  await page.getByLabel("原意见上下文 1", { exact: true }).fill("审稿意见1：请报告研究样本量，并解释抽样范围。");
  await page.getByLabel("作者逐点回复", { exact: true }).fill(reply);
  await page.getByLabel("材料来源与缺口", { exact: true }).fill("全部为自动测试合成材料，回复仅为节选，不代签或作出版决定。");
  for (const label of ["原稿正文完整", "修订稿正文完整", "已包含全部需要核对的意见", "作者回复完整"]) await expect(page.getByRole("checkbox", { name: label, exact: true })).not.toBeChecked();
  await page.getByRole("checkbox", { name: /我确认这些材料为合成/ }).check();
}

test("私人修回：真实版本核对、三层人工判断、导出、刷新和历史版本绑定", async ({ page }) => {
  const fixture = await prepare(page);
  const mutations: string[] = [];
  page.on("request", request => { if (request.method() === "POST") mutations.push(new URL(request.url()).pathname); });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions`);
  await expect(page.getByLabel("询问当前资料")).toBeVisible();
  await fillCheck(page, fixture.base.version_id);
  await page.getByRole("button", { name: "生成修回核对", exact: true }).click();
  await expect(page).toHaveURL(/revision_check=[0-9a-f-]{36}/);
  const checkId = new URL(page.url()).searchParams.get("revision_check")!;
  await expect(page.getByText("Mock 模拟：未运行语义判断。", { exact: true })).toBeVisible();
  const point = page.getByRole("region", { name: "人工判断 P01", exact: true });
  await point.getByRole("combobox", { name: "作者回应", exact: true }).selectOption("addressed");
  await point.getByRole("combobox", { name: "正文落实", exact: true }).selectOption("partial");
  await point.getByRole("combobox", { name: "编辑处理", exact: true }).selectOption("follow_up");
  await point.getByRole("textbox", { name: "本人核对理由", exact: true }).fill("样本量有修改，但抽样范围仍需进一步核对。此为合成个人判断。");
  await expect(point.getByRole("checkbox")).not.toBeChecked();
  await expect(point.getByRole("button", { name: "保存人工判断", exact: true })).toBeDisabled();
  await point.getByRole("checkbox").check();
  await point.getByRole("button", { name: "保存人工判断", exact: true }).click();
  await expect(point.getByRole("status")).toHaveText("人工判断已保存。");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出修回核对 JSON", exact: true }).click();
  const download = await downloadEvent, stream = await download.createReadStream();
  const chunks: Buffer[] = []; for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const exported = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(exported.id).toBe(checkId); expect(exported.reviews.P01.response_verdict).toBe("addressed");
  expect(exported.reviews.P01.implementation_verdict).toBe("partial"); expect(exported.reviews.P01.editor_verdict).toBe("follow_up");
  expect(exported.sources.base.text).toBe(original); expect(exported.sources.revised.text).toBe(revised);
  expect(exported.materials.response_complete).toBe(false);
  await page.reload(); await expect(page.getByText(/已保存判断：已回应；部分落实；需要进一步处理/)).toBeVisible();
  await fixture.save(revised + "\n另一后续修订版。");
  await page.reload(); await expect(page.getByText("这是历史版本的核对包，判断不会自动迁移到当前稿件。", { exact: true })).toBeVisible();
  expect((await (await page.request.get(`/api/dossiers/${fixture.id}/revision-checks/${checkId}`)).json()).base_version_id).toBe(fixture.base.version_id);
  expect(mutations.every(path => !/email|decision|confirmation/.test(path))).toBe(true);
});

test("核对创建丢失响应：主动重试沿同UUID恢复，不重复生成核对包", async ({ page }) => {
  const fixture = await prepare(page);
  const root = `/api/dossiers/${fixture.id}/revision-checks`;
  const bodies: { request_id: string }[] = [];
  await page.route(`**${root}`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) { const response = await route.fetch(); expect(response.status()).toBe(200); await route.abort("failed"); }
    else await route.continue();
  });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions`); await fillCheck(page, fixture.base.version_id);
  await page.getByRole("button", { name: "生成修回核对", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "无法连接资料服务，请检查网络后重试。" })).toHaveText("无法连接资料服务，请检查网络后重试。");
  await page.getByRole("button", { name: "生成修回核对", exact: true }).click();
  await expect(page).toHaveURL(/revision_check=/);
  expect(bodies).toHaveLength(2); expect(bodies[0].request_id).toBe(bodies[1].request_id);
  expect((await (await page.request.get(root)).json()).items).toHaveLength(1);
});

test("核对已写入但读取失败：恢复只GET，不重复POST", async ({ page }) => {
  const fixture = await prepare(page), root = `/api/dossiers/${fixture.id}/revision-checks`;
  let posts = 0, lost = false;
  page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === root) posts++; });
  await page.route(`**${root}/*`, async route => {
    if (!lost && route.request().method() === "GET" && new RegExp(`${root}/[0-9a-f-]{36}$`).test(new URL(route.request().url()).pathname)) { lost = true; await route.abort("failed"); }
    else await route.continue();
  });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions`); await fillCheck(page, fixture.base.version_id);
  await page.getByRole("button", { name: "生成修回核对", exact: true }).click();
  await expect(page.getByRole("button", { name: "恢复已生成核对包", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "恢复已生成核对包", exact: true }).click();
  await expect(page).toHaveURL(/revision_check=/); expect(posts).toBe(1);
});

test("人工判断写后读取失败再刷新历史：重新勾选，恢复不重基或重复写入", async ({ page }) => {
  const fixture = await prepare(page), packet = await fixture.createPacket();
  const url = `/api/dossiers/${fixture.id}/revision-checks/${packet.id}/points/P01/reviews`;
  let posts = 0, lost = false;
  await page.route(`**${url}`, async route => {
    if (route.request().method() === "POST") { posts++; return route.continue(); }
    if (!lost) { lost = true; return route.abort("failed"); }
    return route.continue();
  });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions&revision_check=${packet.id}`);
  const point = page.getByRole("region", { name: "人工判断 P01", exact: true });
  await point.getByRole("combobox", { name: "作者回应", exact: true }).selectOption("addressed");
  await point.getByRole("combobox", { name: "正文落实", exact: true }).selectOption("partial");
  await point.getByRole("combobox", { name: "编辑处理", exact: true }).selectOption("follow_up");
  await point.getByRole("textbox", { name: "本人核对理由", exact: true }).fill("合成样本量已经修改，其他要求尚需核实。只保存个人判断。");
  await point.getByRole("checkbox").check();
  await point.getByRole("button", { name: "保存人工判断", exact: true }).click();
  await expect(point.getByRole("button", { name: "恢复已保存判断", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "重新读取核对包", exact: true }).click();
  await expect(point.getByRole("checkbox")).not.toBeChecked();
  await expect(point.getByRole("textbox", { name: "本人核对理由", exact: true })).toHaveValue("合成样本量已经修改，其他要求尚需核实。只保存个人判断。");
  await point.getByText("人工判断历史", { exact: true }).click();
  await expect(point.getByText(/第 1 次：已回应；部分落实；需要进一步处理/)).toBeVisible();
  await expect(point.getByRole("checkbox")).not.toBeChecked();
  await point.getByRole("checkbox").check();
  await point.getByRole("button", { name: "恢复已保存判断", exact: true }).click();
  await expect(point.getByRole("status")).toHaveText("人工判断已保存。");
  expect(posts).toBe(1);
  expect((await (await page.request.get(url)).json()).items).toHaveLength(1);
});

test("双标签人工判断冲突：重新读取同步head，保留草稿并重新勾选后追加", async ({ page, context }) => {
  const fixture = await prepare(page), packet = await fixture.createPacket();
  const href = `/library?dossier=${fixture.id}&panel=revisions&revision_check=${packet.id}`;
  const other = await context.newPage();
  const pointA = other.getByRole("region", { name: "人工判断 P01", exact: true });
  const pointB = page.getByRole("region", { name: "人工判断 P01", exact: true });
  async function draft(target: typeof pointA, note: string) {
    await target.getByRole("combobox", { name: "作者回应", exact: true }).selectOption("addressed");
    await target.getByRole("combobox", { name: "正文落实", exact: true }).selectOption("partial");
    await target.getByRole("combobox", { name: "编辑处理", exact: true }).selectOption("follow_up");
    await target.getByRole("textbox", { name: "本人核对理由", exact: true }).fill(note);
    await target.getByRole("checkbox").check();
  }
  try {
    await other.goto(href); await expect(pointA).toBeVisible();
    await page.goto(href); await expect(pointB).toBeVisible();
    const noteA = "标签页甲先核对样本量，尚需补足抽样范围。";
    const noteB = "标签页乙保留本人的独立草稿，重新核对后追加意见。";
    await draft(pointB, noteB); await draft(pointA, noteA);
    await pointA.getByRole("button", { name: "保存人工判断", exact: true }).click();
    await expect(pointA.getByRole("status")).toHaveText("人工判断已保存。");
    await pointB.getByRole("button", { name: "保存人工判断", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "此项已有新的人工判断，请重新载入后核对" })).toHaveText("此项已有新的人工判断，请重新载入后核对");
    await page.getByRole("button", { name: "重新读取核对包", exact: true }).click();
    await expect(pointB.getByText(new RegExp(`已保存判断：.*${noteA}`))).toBeVisible();
    await expect(pointB.getByRole("textbox", { name: "本人核对理由", exact: true })).toHaveValue(noteB);
    await expect(pointB.getByRole("combobox", { name: "正文落实", exact: true })).toHaveValue("partial");
    await expect(pointB.getByRole("checkbox")).not.toBeChecked();
    await pointB.getByRole("checkbox").check();
    await pointB.getByRole("button", { name: "保存人工判断", exact: true }).click();
    await expect(pointB.getByRole("status")).toHaveText("人工判断已保存。");
    const history = await (await page.request.get(`/api/dossiers/${fixture.id}/revision-checks/${packet.id}/points/P01/reviews`)).json();
    expect(history.items).toHaveLength(2); expect(history.items[0].reason).toBe(noteB); expect(history.items[1].reason).toBe(noteA);
  } finally { await other.close(); }
});

test("人工判断响应丢失后重读核对包：保留原UUID和head，不重复追加", async ({ page }) => {
  const fixture = await prepare(page), packet = await fixture.createPacket();
  const url = `/api/dossiers/${fixture.id}/revision-checks/${packet.id}/points/P01/reviews`;
  const writes: { request_id: string; expected_review_id: string | null }[] = [];
  await page.route(`**${url}`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    writes.push(route.request().postDataJSON());
    if (writes.length === 1) { const response = await route.fetch(); expect(response.status()).toBe(200); return route.abort("failed"); }
    return route.continue();
  });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions&revision_check=${packet.id}`);
  const point = page.getByRole("region", { name: "人工判断 P01", exact: true });
  await point.getByRole("combobox", { name: "作者回应", exact: true }).selectOption("addressed");
  await point.getByRole("combobox", { name: "正文落实", exact: true }).selectOption("partial");
  await point.getByRole("combobox", { name: "编辑处理", exact: true }).selectOption("follow_up");
  await point.getByRole("textbox", { name: "本人核对理由", exact: true }).fill("合成个人核对，响应丢失后应恢复原来这一次保存。 ");
  await point.getByRole("checkbox").check(); await point.getByRole("button", { name: "保存人工判断", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "无法连接资料服务，请检查网络后重试。" })).toHaveText("无法连接资料服务，请检查网络后重试。");
  await page.getByRole("button", { name: "重新读取核对包", exact: true }).click();
  await expect(point.getByText(/已保存判断：/)).toBeVisible(); await expect(point.getByRole("checkbox")).not.toBeChecked();
  await point.getByRole("checkbox").check(); await point.getByRole("button", { name: "保存人工判断", exact: true }).click();
  await expect(point.getByRole("status")).toHaveText("人工判断已保存。");
  expect(writes).toHaveLength(2); expect(writes[0].request_id).toBe(writes[1].request_id);
  expect(writes[0].expected_review_id).toBeNull(); expect(writes[1].expected_review_id).toBeNull();
  expect((await (await page.request.get(url)).json()).items).toHaveLength(1);
});

test("原文定位校验Unicode/错版本，导出前撤权不下载或恢复旧材料", async ({ page }) => {
  const fixture = await prepare(page), packet = await fixture.createPacket();
  const quote = "样本量改为20", start = Array.from(revised.slice(0, revised.indexOf(quote))).length;
  const citation = { kind: "revised", file_id: randomUUID(), version_id: fixture.current.version_id, version_no: fixture.current.version_no, sha256: createHash("sha256").update(revised).digest("hex"), start, end: start + Array.from(quote).length, quote, line_start: 2, line_end: 2, filename: "same-synthetic-name.txt", download_url: `/api/dossiers/${fixture.id}/versions/${fixture.current.version_id}/file` };
  let wrongVersion = false;
  const url = `/api/dossiers/${fixture.id}/revision-checks/${packet.id}`;
  await page.route(`**${url}`, async route => {
    const response = await route.fetch(), value = await response.json();
    value.report.rows[0].citations = [{ ...citation, version_id: wrongVersion ? fixture.base.version_id : fixture.current.version_id }];
    await route.fulfill({ response, json: value });
  });
  await page.goto(`/library?dossier=${fixture.id}&panel=revisions&revision_check=${packet.id}`);
  await page.getByRole("button", { name: /定位修订稿原文/ }).click();
  await expect(page.getByLabel("修订稿原文定位").locator("mark")).toHaveText(quote);
  wrongVersion = true; await page.reload();
  await page.getByRole("button", { name: /定位修订稿原文/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: "引用文件或版本不匹配，请重新载入核对包。" })).toHaveText("引用文件或版本不匹配，请重新载入核对包。");
  await expect(page.getByLabel("修订稿原文定位")).toHaveCount(0);
  let downloads = 0, exports = 0;
  page.on("download", () => downloads++);
  page.on("request", request => { if (new URL(request.url()).pathname === `${url}/export`) exports++; });
  await page.route("**/api/publishing/session", route => route.fulfill({ status: 403, json: { detail: "合成撤权测试" } }));
  await page.getByRole("button", { name: "导出修回核对 JSON", exact: true }).click();
  await expect(page.getByText("访问权限或身份已变化，请重新登录。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "导出修回核对 JSON", exact: true })).toHaveCount(0);
  expect(downloads).toBe(0); expect(exports).toBe(0);
});
