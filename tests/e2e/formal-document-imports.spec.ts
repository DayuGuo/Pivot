import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
async function start(page: Page) {
    const login = await page.request.post('/api/auth/login', { data: { email: 'author@publishing.test', password: 'AuthorDemo2026!' } });
    expect(login.status()).toBe(200);
    const auth = await login.json();
    const response = await page.request.post('/api/publishing/drafts', { headers: { 'X-CSRF-Token': auth.csrf_token }, data: { request_id: crypto.randomUUID(), title: '合成正式文档浏览器回归' } });
    expect(response.status()).toBe(200);
    return (await response.json()).manuscript_id as string;
}
async function prepare(page: Page, mid: string, extension: 'pdf' | 'docx', filename = `synthetic-manuscript.${extension}`) {
    await page.goto(`/publishing?manuscript=${mid}`);
    await page.getByRole('link', { name: '导入 PDF / Word 并核对', exact: true }).click();
    await expect(page.getByLabel('向出版助手发送消息')).toBeVisible();
    await page.getByLabel('选择 PDF / Word', { exact: true }).setInputFiles(path.resolve(`tests/documents/${filename}`));
    await page.getByLabel('来源与授权说明', { exact: true }).fill('全部为合成接口和浏览器测试材料，无保密或真实受试者资料。');
    await page.getByRole('checkbox', { name: '我有权使用此资料', exact: false }).check();
    await page.getByRole('button', { name: '提取并打开核对页', exact: true }).click();
    await expect(page.getByRole('heading', { name: '核对导入文件', exact: true })).toBeVisible();
    await expect(page.getByLabel('待保存的提取全文', { exact: true })).toHaveValue(/Synthetic/);
}
async function acknowledge(page: Page) {
    await page.getByRole('checkbox', { name: '我已核对原件及其来源授权', exact: true }).check();
    await page.getByRole('checkbox', { name: '我已对照原件核对提取全文，没有漏页或漏段', exact: true }).check();
    await page.getByRole('checkbox', { name: '我已核对所选范围符合文件用途，不混入评审附录或其他材料', exact: true }).check();
}
for (const extension of ['pdf', 'docx'] as const)
    test(`正式${extension}：提取不入版，人工核对后持久化，常驻对话与原件`, async ({ page }) => {
        const mid = await start(page);
        await prepare(page, mid, extension);
        const before = await (await page.request.get(`/api/publishing/manuscripts/${mid}`)).json();
        expect(before.version.files).toHaveLength(0);
        const button = page.getByRole('button', { name: '确认导入到当前草稿', exact: true });
        await expect(button).toBeDisabled();
        await acknowledge(page);
        await button.click();
        await expect(page.getByRole('status').filter({ hasText: '已保存到绑定草稿' })).toBeVisible();
        const after = await (await page.request.get(`/api/publishing/manuscripts/${mid}`)).json();
        expect(after.stage).toBe('author_draft');
        expect(after.version.id).toBe(before.version.id);
        expect(after.version.files).toHaveLength(1);
        const original = await page.request.get(`/api/publishing/files/${after.version.files[0].id}/original`);
        expect(original.status()).toBe(200);
        await page.reload();
        await expect(page.getByRole('status').filter({ hasText: '已保存到绑定草稿' })).toBeVisible();
        await expect(page.getByLabel('向出版助手发送消息')).toBeVisible();
        await expect(page.getByText(`${after.number} · ${after.stage_label}`,{exact:false})).toBeVisible();
        await page.screenshot({ path: test.info().outputPath(`formal-${extension}-desktop.png`) });
        await page.setViewportSize({ width: 375, height: 812 });
        await expect(page.getByLabel('向出版助手发送消息')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: test.info().outputPath(`formal-${extension}-mobile.png`) });
    });
test('确认响应丢失复用UUID，不重复保存；更改范围重置核对', async ({ page }) => {
    const mid = await start(page);
    await prepare(page, mid, 'docx');
    await acknowledge(page);
    await page.getByLabel('正文起始段落', { exact: true }).fill('2');
    await expect(page.getByRole('checkbox', { name: '我已对照原件核对提取全文，没有漏页或漏段', exact: true })).not.toBeChecked();
    await acknowledge(page);
    const ids: string[] = [];
    let drop = true;
    await page.route('**/document-imports/*/confirmations', async (route) => { ids.push(route.request().postDataJSON().request_id); const response = await route.fetch(); if (drop) {
        drop = false;
        await route.abort('failed');
    }
    else
        await route.fulfill({ response }); });
    await page.getByRole('button', { name: '确认导入到当前草稿', exact: true }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await page.getByRole('button', { name: '确认导入到当前草稿', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: '已保存到绑定草稿' })).toBeVisible();
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);
    const detail = await (await page.request.get(`/api/publishing/manuscripts/${mid}`)).json();
    expect(detail.revision).toBe(1);
    expect(detail.version.files).toHaveLength(1);
});

test('Unicode数学符号和emoji范围核对与保存一致，刷新仍显示批准范围', async({page})=>{
 const mid=await start(page);await prepare(page,mid,'docx','synthetic-unicode.docx');
 await page.getByLabel('正文起始段落',{exact:true}).fill('2');await page.getByLabel('正文结束段落',{exact:true}).fill('2');
 const expected='第二段：𝛽 和 😀 均须完整保留。';
 await expect(page.getByLabel('待保存的提取全文',{exact:true})).toHaveValue(expected);
 await acknowledge(page);await page.getByRole('button',{name:'确认导入到当前草稿',exact:true}).click();
 await expect(page.getByLabel('已保存的提取全文',{exact:true})).toHaveValue(expected);
 await page.reload();await expect(page.getByLabel('已保存的提取全文',{exact:true})).toHaveValue(expected);
 await expect(page.getByLabel('正文起始段落',{exact:true})).toHaveValue('2');await expect(page.getByLabel('正文结束段落',{exact:true})).toHaveValue('2');
 const detail=await(await page.request.get(`/api/publishing/manuscripts/${mid}`)).json();
 const saved=await page.request.get(`/api/publishing/files/${detail.version.files[0].id}`);expect(await saved.text()).toBe(expected);
});

test('刷新后找回待核对导入；非整数范围不可保存', async ({page})=>{
 const mid=await start(page);await prepare(page,mid,'docx');
 await page.goto(`/publishing/document-imports/${mid}/new`);
 await expect(page.getByRole('heading',{name:'继续核对',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'synthetic-manuscript.docx',exact:true}).click();
 await expect(page.getByLabel('待保存的提取全文',{exact:true})).toHaveValue(/Synthetic/);
 await page.getByLabel('正文起始段落',{exact:true}).fill('1.5');
 await expect(page.getByRole('alert').filter({hasText:'请选择有效的正文范围'})).toBeVisible();
 await expect(page.getByRole('button',{name:'确认导入到当前草稿',exact:true})).toBeDisabled();
 const detail=await(await page.request.get(`/api/publishing/manuscripts/${mid}`)).json();expect(detail.revision).toBe(0);expect(detail.version.files).toHaveLength(0);
});

test('确认时权限失败清除原文和勾选；恢复必须重新核对', async({page})=>{
 const mid=await start(page);await prepare(page,mid,'docx');await acknowledge(page);
 await page.route('**/document-imports/*/confirmations',route=>route.fulfill({status:403,json:{detail:'合成撤权回归：导入确认权限已撤销'}}));
 await page.getByRole('button',{name:'确认导入到当前草稿',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'导入确认权限已撤销'})).toBeVisible();
 await expect(page.getByLabel('待保存的提取全文',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('checkbox',{name:'我已核对原件及其来源授权',exact:true})).toHaveCount(0);
 await page.unroute('**/document-imports/*/confirmations');
 await page.getByRole('button',{name:'重新载入导入记录',exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'我已核对原件及其来源授权',exact:true})).not.toBeChecked();
 await expect(page.getByRole('button',{name:'确认导入到当前草稿',exact:true})).toBeDisabled();
});

async function citedUnicodeSource(page:Page){
 const mid=await start(page);await prepare(page,mid,'docx','synthetic-unicode.docx');
 const iid=new URL(page.url()).pathname.split('/').at(-1)!;
 const imported=await(await page.request.get(`/api/publishing/manuscripts/${mid}/document-imports/${iid}`)).json();
 await page.getByLabel('正文起始段落',{exact:true}).fill('2');await page.getByLabel('正文结束段落',{exact:true}).fill('2');await acknowledge(page);await page.getByRole('button',{name:'确认导入到当前草稿',exact:true}).click();
 await expect(page.getByLabel('已保存的提取全文',{exact:true})).toHaveValue('第二段：𝛽 和 😀 均须完整保留。');
 const detail=await(await page.request.get(`/api/publishing/manuscripts/${mid}`)).json(),file=detail.version.files[0];
 const full='第二段：𝛽 和 😀 均须完整保留。',quote='😀 均须完整保留';const quoteStart=Array.from(full.slice(0,full.indexOf(quote))).length,quoteEnd=quoteStart+Array.from(quote).length;
 const report={schema:'revision-comparison.v1',provider:'mock',base_version_id:'synthetic-old',revised_version_id:detail.version.id,workflow_revision:detail.revision,point_count:1,all_points_included:true,rereview_required:false,coverage:{revised:{read_characters:Array.from(full).length,total_characters:Array.from(full).length,complete:true}},rows:[{point_id:'P01',status:'uncertain',reason:'合成浏览器夹具，仅验证实际导入原文的定位，不作科学判断。',point:{text:'合成核对要求',label:'合成界面验收',complete:true},citations:[{kind:'revised',file_id:file.id,start:quoteStart,end:quoteEnd,version_no:1,quote,line_start:1,line_end:1,sha256:file.sha256,original:{filename:'synthetic-unicode.docx',sha256:imported.sha256,download_url:`/api/publishing/files/${file.id}/original`,locations:[{kind:'docx_paragraph',number:2,quote}]}}]}]};
 await page.route('**/api/publishing/chat*',route=>{expect(route.request().method()).toBe('GET');return route.fulfill({json:{messages:[{id:'synthetic-source-locator',role:'assistant',provider:'mock',created_at:'2026-11-05T00:00:00Z',content:'明确合成原文定位夹具',references:[],tool_receipts:[],action:null,revision_comparison:report}]}});});
 await page.goto(`/publishing?manuscript=${mid}`);await page.getByText('核对原文依据（1）',{exact:true}).click();
 return {file,quote};
}

test('引文定位真实已核对Word全文，高亮Unicode并保留原件下载',async({page})=>{
 const {quote}=await citedUnicodeSource(page);let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});
 await page.getByRole('button',{name:'定位已核对全文',exact:true}).click();
 const mark=page.getByLabel('已定位原文引用',{exact:true});await expect(mark).toHaveText(quote);await expect(mark).toBeFocused();
 await expect(page.getByRole('link',{name:'Word 第2段 · 下载原件',exact:true})).toBeVisible();expect(posts).toBe(0);
 await page.screenshot({path:test.info().outputPath('word-source-desktop.png')});
 await page.getByLabel('外观',{exact:true}).selectOption('dark');await page.setViewportSize({width:375,height:812});await mark.scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:test.info().outputPath('word-source-mobile-dark.png')});
});

test('等待原件期间切换身份，迟到的已核对全文不显示',async({page})=>{
 const {file}=await citedUnicodeSource(page);let release!:()=>void,held=false;const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route(`**/api/publishing/files/${file.id}/original`,async route=>{const response=await route.fetch();held=true;await gate;await route.fulfill({response});});
 await page.getByRole('button',{name:'定位已核对全文',exact:true}).click();await expect.poll(()=>held).toBe(true);
 const changed=await page.request.post('/api/auth/login',{data:{email:'editor@publishing.test',password:'EditorDemo2026!'}});expect(changed.status()).toBe(200);release();
 await expect(page.getByRole('alert').filter({hasText:'身份或访问权限已变化'})).toBeVisible();await expect(page.getByLabel('已定位原文引用',{exact:true})).toHaveCount(0);
});

test('文件字节被篡改，SHA不符不展示引用上下文',async({page})=>{
 const {file}=await citedUnicodeSource(page);
 await page.route(`**/api/publishing/files/${file.id}`,route=>route.fulfill({status:200,contentType:'text/plain;charset=utf-8',body:'不是绑定版本的原文。'}));
 await page.getByRole('button',{name:'定位已核对全文',exact:true}).click();
 await expect(page.getByRole('alert').filter({hasText:'原文校验未通过'})).toBeVisible();await expect(page.getByLabel('已定位原文引用',{exact:true})).toHaveCount(0);
});

test('确认导入成功后先恢复核对记录，不等待工作列表刷新', async ({ page }) => {
  const mid = await start(page); await prepare(page, mid, 'docx'); await acknowledge(page);
  let release!: () => void; const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/publishing/workspace', async route => { await waiting; return route.continue(); });
  try {
    await page.getByRole('button', { name: '确认导入到当前草稿', exact: true }).click();
    await expect(page.getByLabel('已保存的提取全文', { exact: true })).toHaveValue(/Synthetic/);
  } finally { release(); }
});
