import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

type Role = "editor" | "chief_editor" | "reviewer" | "author";
type Identity = { active_role: Role; roles: string[]; csrf_token: string; user: { id: string; role: Role } };
const labels: Record<Role, string> = { editor: "编辑", chief_editor: "主编", reviewer: "审稿人", author: "作者" };
const titles: Record<Role, string> = { editor: "待我处理的稿件", chief_editor: "期刊稿件", reviewer: "我的审稿邀请", author: "我的投稿" };

// Real local-demo authentication and deterministic business endpoints only.
// These cases never send chat commands, call models, or send mail.
async function login(page: Page, account: "multi" | "reviewer" = "multi") {
  const response = await page.request.post("/api/auth/login", {
    data: { email: `${account}@publishing.test`, password: account === "multi" ? "MultiDemo2026!" : "ReviewerDemo2026!" },
  });
  expect(response.status()).toBe(200);
  return identity(page);
}

async function identity(page: Page): Promise<Identity> {
  const response = await page.request.get("/api/auth/identities");
  expect(response.status()).toBe(200);
  return response.json();
}

async function openIdentities(page: Page) {
  const summary = page.locator('summary[aria-label="切换身份"]');
  await summary.click();
  const list = page.getByRole("list", { name: "当前账号的可用身份", exact: true });
  await expect(list).toBeVisible();
  return list;
}

async function switchTo(page: Page, role: Role) {
  const list = await openIdentities(page);
  await list.getByRole("link", { name: labels[role], exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/identity\\?role=${role}$`));
  await expect(page.getByRole("heading", { name: "切换身份", exact: true })).toBeVisible();
  const completed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/identity" && response.request().method() === "POST");
  await page.getByRole("button", { name: `切换为${labels[role]}`, exact: true }).click();
  expect((await completed).status()).toBe(200);
  await expect(page).toHaveURL(/\/publishing$/);
  await expect(page.getByRole("heading", { name: titles[role], exact: true })).toBeVisible();
  const current = await identity(page);
  expect(current.active_role).toBe(role);
  return current;
}

function countIdentityPosts(page: Page) {
  const roles: string[] = [];
  page.on("request", request => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/auth/identity") roles.push(request.postDataJSON().role);
  });
  return roles;
}

test("多身份：真实账号独立确认后依次切换主编、审稿人、作者并返回编辑", async ({ page }) => {
  test.setTimeout(60000);
  let previous = await login(page);
  expect(previous.active_role).toBe("editor");
  expect([...previous.roles].sort()).toEqual(["author", "chief_editor", "editor", "reviewer"]);
  await page.goto("/publishing");
  await expect(page.getByRole("heading", { name: titles.editor, exact: true })).toBeVisible();
  const posts = countIdentityPosts(page);
  for (const role of ["chief_editor", "reviewer", "author", "editor"] as const) {
    const current = await switchTo(page, role);
    expect(current.user.id === previous.user.id).toBe(true);
    expect(current.csrf_token !== previous.csrf_token).toBe(true);
    previous = current;
  }
  expect(posts).toEqual(["chief_editor", "reviewer", "author", "editor"]);
});

test("当前身份只显示当前标记，直接打开同一身份不产生切换请求", async ({ page }) => {
  const before = await login(page);
  await page.goto("/publishing");
  const posts = countIdentityPosts(page);
  const list = await openIdentities(page);
  await expect(list.locator('[aria-current="true"]')).toContainText("编辑");
  await expect(list.getByRole("link", { name: "编辑", exact: true })).toHaveCount(0);
  await page.goto("/identity?role=editor");
  await expect(page.getByText("当前已是编辑。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^切换为/ })).toHaveCount(0);
  await page.getByRole("link", { name: "进入工作区", exact: true }).click();
  await expect(page.getByRole("heading", { name: titles.editor, exact: true })).toBeVisible();
  const after = await identity(page);
  expect(after.active_role).toBe("editor");
  expect(after.csrf_token === before.csrf_token).toBe(true);
  expect(posts).toEqual([]);
});

test("单身份审稿人不能选择或直接请求未经授予的编辑身份", async ({ page }) => {
  const before = await login(page, "reviewer");
  await page.goto("/publishing");
  const posts = countIdentityPosts(page);
  const list = await openIdentities(page);
  await expect(list.locator("li")).toHaveCount(1);
  await expect(list.locator('[aria-current="true"]')).toContainText("审稿人");
  await expect(list.getByRole("link")).toHaveCount(0);
  await page.goto("/identity?role=editor");
  await expect(page.getByRole("main").getByRole("alert").filter({ hasText: "当前账号没有这个可用身份，请返回工作区重新选择。" })).toHaveText("当前账号没有这个可用身份，请返回工作区重新选择。");
  await expect(page.getByRole("button", { name: "切换为编辑", exact: true })).toHaveCount(0);
  const forbidden = await page.request.post("/api/auth/identity", {
    headers: { "X-CSRF-Token": before.csrf_token }, data: { role: "editor", request_id: randomUUID() },
  });
  expect(forbidden.status()).toBe(403);
  const after = await identity(page);
  expect(after.active_role).toBe("reviewer");
  expect(after.csrf_token === before.csrf_token).toBe(true);
  expect(posts).toEqual([]);
});

test("作者取消离开未保存资料时保留草稿和身份，切换 POST 尚未发送", async ({ page }) => {
  await login(page); await page.goto("/publishing");
  const auth = await switchTo(page, "author");
  const created = await page.request.post("/api/publishing/drafts", {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: { request_id: randomUUID(), title: "完全合成的身份切换离开保护" },
  });
  expect(created.status()).toBe(200);
  const mid = (await created.json()).manuscript_id;
  await page.goto(`/publishing?manuscript=${mid}`);
  const draft = "尚未保存的合成作者题名，不应因取消切换而丢失";
  await page.getByLabel("标题", { exact: true }).fill(draft);
  const beforeURL = page.url();
  const posts = countIdentityPosts(page);
  const list = await openIdentities(page);
  const leaving = page.waitForEvent("dialog");
  const navigation = list.getByRole("link", { name: "编辑", exact: true }).click({ noWaitAfter: true });
  const dialog = await leaving;
  expect(["confirm", "beforeunload"]).toContain(dialog.type());
  await dialog.dismiss(); await navigation;
  await expect(page).toHaveURL(beforeURL);
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(draft);
  const after = await identity(page);
  expect(after.active_role).toBe("author");
  expect(after.csrf_token === auth.csrf_token).toBe(true);
  expect(posts).toEqual([]);
});

test("作者仅选择未上传文件时取消切换保留文件，再确认离开才打开独立身份页", async ({ page }) => {
  await login(page); await page.goto("/publishing");
  const auth = await switchTo(page, "author");
  const title = "完全合成的未上传文件离开保护";
  const created = await page.request.post("/api/publishing/drafts", {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: { request_id: randomUUID(), title },
  });
  expect(created.status()).toBe(200);
  const mid = (await created.json()).manuscript_id;
  await page.goto(`/publishing?manuscript=${mid}`);
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(title);
  const upload = page.getByLabel("选择文件", { exact: true });
  await upload.setInputFiles({ name: "identity-not-uploaded.txt", mimeType: "text/plain", buffer: Buffer.from("完全合成的本地文件，仅选择，不上传。", "utf8") });
  const beforeURL = page.url();
  const posts = countIdentityPosts(page);
  let list = await openIdentities(page);
  const leaving = page.waitForEvent("dialog");
  const navigation = list.getByRole("link", { name: "编辑", exact: true }).click({ noWaitAfter: true });
  const dialog = await leaving;
  expect(["confirm", "beforeunload"]).toContain(dialog.type());
  await dialog.dismiss(); await navigation;
  await expect(page).toHaveURL(beforeURL);
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(title);
  expect(await upload.evaluate(input => Array.from((input as HTMLInputElement).files ?? []).map(file => file.name))).toEqual(["identity-not-uploaded.txt"]);
  const current = await identity(page);
  expect(current.active_role).toBe("author");
  expect(current.csrf_token === auth.csrf_token).toBe(true);
  const saved = await page.request.get(`/api/publishing/manuscripts/${mid}`);
  expect(saved.status()).toBe(200);
  expect((await saved.json()).version.files).toHaveLength(0);
  expect(posts).toEqual([]);

  if (!await list.isVisible()) list = await openIdentities(page);
  let acceptedPrompts = 0;
  page.once("dialog", async prompt => { acceptedPrompts += 1; await prompt.accept(); });
  await list.getByRole("link", { name: "编辑", exact: true }).click();
  await expect(page).toHaveURL(/\/identity\?role=editor$/);
  await expect(page.getByRole("button", { name: "切换为编辑", exact: true })).toBeEnabled();
  expect(acceptedPrompts).toBe(1);
  expect((await identity(page)).active_role).toBe("author");
  expect(posts).toEqual([]);
});

test("另一标签页切换身份后关闭旧私人资料和未保存草稿，只读进入新身份", async ({ page, context }) => {
  test.setTimeout(60000);
  const auth = await login(page);
  const created = await page.request.post("/api/dossiers", {
    headers: { "X-CSRF-Token": auth.csrf_token },
    data: { request_id: randomUUID(), title: "完全合成的跨标签私人资料", source_kind: "synthetic", source_note: "全部为本地身份边界测试原创合成内容。", authorized_material: true },
  });
  expect(created.status()).toBe(200);
  const id = (await created.json()).dossier_id;
  await page.goto(`/library?dossier=${id}`);
  await page.getByLabel("题名", { exact: true }).fill("仅在旧标签页的未保存合成私人草稿");
  await expect(page.getByLabel("询问当前资料", { exact: true })).toBeVisible();
  const oldPosts = countIdentityPosts(page);
  const other = await context.newPage();
  try {
    await other.goto("/publishing");
    const otherPosts = countIdentityPosts(other);
    for (const role of ["reviewer", "author"] as const) {
      await switchTo(other, role);
      // Broadcast invalidation must work while this tab remains in the background,
      // without polling, reloading it, or forcing a focus event from the harness.
      await expect(page.getByRole("heading", { name: "当前身份已变化", exact: true })).toBeVisible({ timeout: 5000 });
      await expect(page.getByLabel("题名", { exact: true })).toHaveCount(0);
      await expect(page.getByLabel("询问当前资料", { exact: true })).toHaveCount(0);
      await expect(page.locator('summary[aria-label="切换身份"]')).toHaveCount(0);
      expect(oldPosts).toEqual([]);
      await page.getByRole("link", { name: "进入当前身份工作区", exact: true }).click();
      await expect(page.getByRole("heading", { name: titles[role], exact: true })).toBeVisible();
      expect((await identity(page)).active_role).toBe(role);
      expect(oldPosts).toEqual([]);
    }
    expect(otherPosts).toEqual(["reviewer", "author"]);
  } finally { await other.close(); }
});

for (const mismatch of ["user", "role"] as const) {
  test(`身份菜单拒绝${mismatch === "user" ? "不同账号" : "不同活动身份"}的读取结果，不展示错误选项`, async ({ page }) => {
    const before = await login(page);
    await page.goto("/publishing");
    await expect(page.locator('summary[aria-label="切换身份"]')).toBeVisible();
    const posts = countIdentityPosts(page);
    await page.route("**/api/auth/identities", async route => {
      const response = await route.fetch();
      const snapshot = await response.json();
      await route.fulfill({ json: mismatch === "user"
        ? { ...snapshot, user: { ...snapshot.user, id: "synthetic-unexpected-account" } }
        : { ...snapshot, active_role: "reviewer", user: { ...snapshot.user, role: "reviewer" } },
      });
    }, { times: 1 });
    await page.locator('summary[aria-label="切换身份"]').click();
    const control = page.locator("details").filter({ has: page.locator('summary[aria-label="切换身份"]') });
    await expect(control.getByRole("alert").filter({ hasText: "当前身份已变化，请重新打开工作区。" })).toHaveText("当前身份已变化，请重新打开工作区。");
    await expect(page.getByRole("list", { name: "当前账号的可用身份", exact: true })).toHaveCount(0);
    await expect(page.locator('a[href^="/identity?role="]')).toHaveCount(0);
    const after = await identity(page);
    expect(after.active_role).toBe("editor");
    expect(after.user.id === before.user.id).toBe(true);
    expect(posts).toEqual([]);
  });
}

test("已提交切换的回执中断后只显式读取当前身份，不自动重发 POST", async ({ page }) => {
  await login(page); await page.goto("/identity?role=chief_editor");
  await expect(page.getByRole("button", { name: "切换为主编", exact: true })).toBeEnabled();
  const posts = countIdentityPosts(page);
  let committed = false;
  await page.route("**/api/auth/identity", async route => {
    // The real server commits and rotates its cookie. Interrupt only the receipt
    // delivered to the page; recovery must inspect the shared current session.
    const result = await route.fetch();
    expect(result.status()).toBe(200); committed = true;
    await route.abort("connectionreset");
  }, { times: 1 });
  await page.getByRole("button", { name: "切换为主编", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert").filter({ hasText: "切换结果尚未确认。请先核对当前身份，再决定是否重试。" })).toHaveText("切换结果尚未确认。请先核对当前身份，再决定是否重试。");
  expect(committed).toBe(true);
  expect(posts).toEqual(["chief_editor"]);
  await expect(page.getByRole("button", { name: /^切换为/ })).toHaveCount(0);
  const checked = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/identities" && response.request().method() === "GET");
  await page.getByRole("button", { name: "核对当前身份", exact: true }).click();
  expect((await checked).status()).toBe(200);
  await expect(page.getByText("当前已是主编。", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "进入工作区", exact: true }).click();
  await expect(page.getByRole("heading", { name: titles.chief_editor, exact: true })).toBeVisible();
  expect((await identity(page)).active_role).toBe("chief_editor");
  expect(posts).toEqual(["chief_editor"]);
});

test("所有真实工作区提供可键盘操作的原生身份链接，Escape 关闭并恢复焦点", async ({ page }) => {
  test.setTimeout(60000);
  await login(page);
  const posts = countIdentityPosts(page);
  for (const path of ["/", "/library", "/publishing", "/workbench"]) {
    await page.goto(path);
    const summary = page.locator('summary[aria-label="切换身份"]');
    await expect(summary).toBeVisible();
    await summary.focus(); await page.keyboard.press("Enter");
    const list = page.getByRole("list", { name: "当前账号的可用身份", exact: true });
    await expect(list).toBeVisible();
    const target = list.getByRole("link", { name: "主编", exact: true });
    await expect(target).toHaveAttribute("href", "/identity?role=chief_editor");
    await target.focus(); await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
    await expect(summary).toBeFocused();
  }
  await page.goto("/publishing");
  const list = await openIdentities(page);
  await page.screenshot({ path: `artifacts/identity/${test.info().project.name}-desktop-menu.png`, fullPage: true });
  await list.getByRole("link", { name: "主编", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/identity\?role=chief_editor$/);
  await expect(page.getByRole("button", { name: "切换为主编", exact: true })).toBeEnabled();
  expect((await identity(page)).active_role).toBe("editor");
  expect(posts).toEqual([]);
});

test("390px 深色身份菜单可读可点击，选择后关闭工作列表并保留独立确认", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page); await page.goto("/publishing");
  const posts = countIdentityPosts(page);
  await page.getByRole("button", { name: "打开工作列表", exact: true }).click();
  await page.getByLabel("外观", { exact: true }).selectOption("dark");
  const list = await openIdentities(page);
  const target = list.getByRole("link", { name: "主编", exact: true });
  await expect(target).toBeInViewport();
  expect(await target.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `artifacts/identity/${test.info().project.name}-390-dark-menu.png`, fullPage: true });
  await target.click();
  await expect(page.getByRole("heading", { name: "切换身份", exact: true })).toBeVisible();
  await expect(page.locator('main[data-theme="dark"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "关闭工作列表", exact: true })).toHaveCount(0);
  const confirm = page.getByRole("button", { name: "切换为主编", exact: true });
  await expect(confirm).toBeInViewport();
  expect(await confirm.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: `artifacts/identity/${test.info().project.name}-390-dark-confirmation.png`, fullPage: true });
  expect((await identity(page)).active_role).toBe("editor");
  expect(posts).toEqual([]);
});
