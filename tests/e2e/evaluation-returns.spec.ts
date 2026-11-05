import {test,expect,type Page} from '@playwright/test';
import type {RegisteredPacket} from '../../apps/web/components/library/evaluation-types';

async function setup(page:Page){
 const login=await page.request.post('/api/auth/login',{data:{email:'editor@publishing.test',password:'EditorDemo2026!'}});expect(login.status()).toBe(200);const auth=await login.json();
 const headers={'X-CSRF-Token':auth.csrf_token};
 const created=await page.request.post('/api/dossiers',{headers,data:{request_id:crypto.randomUUID(),title:'合成独立评价回传 '+Date.now(),source_kind:'synthetic',source_note:'自动化合成数据，无任何保密材料。',authorized_material:true}});expect(created.status()).toBe(200);
 const id=(await created.json()).dossier_id;
 let current=await (await page.request.get(`/api/dossiers/${id}`)).json();
 const data={...current.data,abstract:'这是一份完整合成测试摘要，仅用于验证独立评价人工核对和原文引用，不包含真实临床参与者或保密资料。',language:'zh',keywords:['合成'],authors:[{name:'合成评价作者',email:'author@synthetic.test',affiliations:['合成机构'],orcid:null,corresponding:true,contributions:[],source_note:'完全合成资料'}]};
 const fulltext='# 合成方法\n本研究仅为合成数据演示，采用随机分组，不包含真实受试者。\n结论不能用于真实临床决策。';
 const saved=await page.request.post(`/api/dossiers/${id}/versions`,{headers,data:{request_id:crypto.randomUUID(),expected_revision:current.revision,data,file:{filename:'synthetic.md',content_base64:Buffer.from(fulltext).toString('base64')}}});expect(saved.status()).toBe(200);
 current=await (await page.request.get(`/api/dossiers/${id}`)).json();
 const answered=await page.request.post(`/api/dossiers/${id}/chat`,{headers,data:{request_id:crypto.randomUUID(),version_id:current.version_id,expected_revision:current.revision,message:'概括合成方法并引用原文。'}});expect(answered.status()).toBe(200);const answer=await answered.json();
 return {id,headers,answer,current};
}
async function download(page:Page){const event=page.waitForEvent('download');await page.getByRole('button',{name:'下载已登记评价包',exact:true}).click();const file=await event;const stream=await file.createReadStream();expect(stream).not.toBeNull();const chunks:Buffer[]=[];for await(const c of stream!)chunks.push(Buffer.from(c));return JSON.parse(Buffer.concat(chunks).toString('utf8')) as RegisteredPacket;}
async function uploadResult(page:Page,packet:RegisteredPacket,verdict:'supported'|'unsupported'){
 const result=structuredClone(packet);for(const c of result.claims)c.assessment={verdict,note:'自动验收模拟负责人：已对照本版原文，记录此评价。'};
 await page.getByLabel('上传评价结果',{exact:true}).setInputFiles({name:'evaluation-return.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(result))});
 await expect(page.getByRole('status').filter({hasText:'预览：'})).toBeVisible();
 return result;
}
async function checkAll(page:Page){const boxes=page.getByRole('checkbox');for(const checkbox of await boxes.all())await checkbox.check();}

test('独立评价真实链：登记下载、逐条核对、保存刷新与分歧统计',async({page})=>{
 test.setTimeout(90000);const w=await setup(page);const before=await (await page.request.get(`/api/dossiers/${w.id}`)).json();
 await page.goto(`/library?dossier=${w.id}`);
 await page.getByRole('button',{name:'独立评价回传',exact:true}).click();
 await page.getByLabel('评价代号',{exact:true}).fill('reader-a');await page.getByRole('button',{name:'登记评价包',exact:true}).click();
 await page.getByRole('link',{name:'reader-a · 下载与核对回传',exact:true}).click();
 await expect(page.getByLabel('询问当前资料')).toBeVisible();
 const packet=await download(page);expect(packet.schema).toBe('claim-evaluation-package.v2');expect(packet.source.version_id).toBe(w.current.version_id);
 await uploadResult(page,packet,'supported');
 const confirm=page.getByRole('button',{name:'确认评价回传',exact:true});await expect(confirm).toBeDisabled();
 await page.getByRole('button',{name:/定位评价引文：/}).first().click();await expect(page.getByLabel('已定位评价原文')).toBeVisible();
 await page.screenshot({path:'artifacts/spec023/return-review-desktop.png'});
 await checkAll(page);await confirm.click();await expect(page.getByRole('status').filter({hasText:'评价回传已确认保存'})).toBeVisible();
 await page.reload();await expect(page.getByLabel('询问当前资料')).toBeVisible();await page.getByText('回传历史',{exact:true}).click();await expect(page.getByText(/第 1 次/)).toBeVisible();
 expect(await (await page.request.get(`/api/dossiers/${w.id}`)).json()).toEqual(before);
 const issued=await page.request.post(`/api/dossiers/${w.id}/answers/${w.answer.id}/evaluations`,{headers:w.headers,data:{request_id:crypto.randomUUID(),evaluator_code:'reader-b',content_digest:w.current.content_digest}});expect(issued.status()).toBe(200);const pk=(await issued.json()).id;
 await page.goto(`/library/evaluation/${pk}?dossier=${w.id}`);const other=await download(page);await uploadResult(page,other,'unsupported');await checkAll(page);await page.getByRole('button',{name:'确认评价回传',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'评价回传已确认保存'})).toBeVisible();
 await page.getByRole('link',{name:'返回资料',exact:true}).click();await page.getByRole('button',{name:'独立评价回传',exact:true}).click();
 await expect(page.getByText(/2 \/ 2 个代号已回传/)).toBeVisible();await expect(page.getByText(/有依据 1 · 无依据 1/).first()).toBeVisible();
 await page.getByRole('heading',{name:'已确认评价的分歧',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'artifacts/spec023/disagreement-desktop.png'});await page.setViewportSize({width:375,height:812});expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);await page.getByRole('heading',{name:'已确认评价的分歧',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'artifacts/spec023/disagreement-mobile.png'});
 const detail=await (await page.request.get(`/api/dossiers/${w.id}/evaluations/${packet.package_id}`)).json();
 const corrected=structuredClone(packet);for(const c of corrected.claims)c.assessment={verdict:'uncertain',note:'并发测试：原文支持仍有疑问，需要继续核对。'};
 const preview=await (await page.request.post(`/api/dossiers/${w.id}/evaluations/${packet.package_id}/preview`,{headers:w.headers,data:{packet:corrected}})).json();
 const attempts=await Promise.all([1,2].map(()=>page.request.post(`/api/dossiers/${w.id}/evaluations/${packet.package_id}/confirm`,{headers:w.headers,data:{request_id:crypto.randomUUID(),packet:corrected,preview_digest:preview.digest,expected_return_id:detail.latest.id,acknowledged:true,acknowledged_claims:corrected.claims.map(c=>c.id)}})));
 expect(attempts.map(r=>r.status()).sort()).toEqual([200,409]);
 expect((await (await page.request.get(`/api/dossiers/${w.id}/evaluations/${packet.package_id}/returns`)).json()).items.map((r:{return_no:number})=>r.return_no)).toEqual([2,1]);

});

test('评价回传：确认回执丢失保留同UUID，改文件重置所有核对',async({page})=>{
 const w=await setup(page);const issued=await page.request.post(`/api/dossiers/${w.id}/answers/${w.answer.id}/evaluations`,{headers:w.headers,data:{request_id:crypto.randomUUID(),evaluator_code:'retry-test',content_digest:w.current.content_digest}});const pk=(await issued.json()).id;
 await page.goto(`/library/evaluation/${pk}?dossier=${w.id}`);const packet=await download(page);await uploadResult(page,packet,'supported');await checkAll(page);
 const requests:Record<string,unknown>[]=[];let first=true;
 await page.route(`**/api/dossiers/${w.id}/evaluations/${pk}/confirm`,async route=>{requests.push(route.request().postDataJSON());const response=await route.fetch();if(first){first=false;return route.fulfill({status:200,json:{}});}return route.fulfill({response});});
 await page.getByRole('button',{name:'确认评价回传',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'未完整收到确认回执'})).toBeVisible();
 await page.getByRole('button',{name:'确认评价回传',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'评价回传已确认保存'})).toBeVisible();expect(requests[0].request_id).toBe(requests[1].request_id);
 await uploadResult(page,packet,'unsupported');await expect(page.getByRole('checkbox').first()).not.toBeChecked();await expect(page.getByRole('button',{name:'确认评价回传',exact:true})).toBeDisabled();
});

test('登记评价包：等待下载期间切换身份清除材料，不下载旧响应',async({page})=>{
 const w=await setup(page);const issued=await page.request.post(`/api/dossiers/${w.id}/answers/${w.answer.id}/evaluations`,{headers:w.headers,data:{request_id:crypto.randomUUID(),evaluator_code:'identity-test',content_digest:w.current.content_digest}});const pk=(await issued.json()).id;
 await page.goto(`/library/evaluation/${pk}?dossier=${w.id}`);await expect(page.getByRole('button',{name:'下载已登记评价包',exact:true})).toBeEnabled();
 const session=await (await page.request.get('/api/publishing/session')).json();
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});let downloads=0;page.on('download',()=>++downloads);
 await page.route(`**/api/dossiers/${w.id}/evaluations/${pk}/file`,async route=>{const response=await route.fetch();await gate;await route.fulfill({response});});
 const requested=page.waitForRequest(r=>r.url().endsWith(`/${pk}/file`));await page.getByRole('button',{name:'下载已登记评价包',exact:true}).click();await requested;
 await page.route('**/api/publishing/session',route=>route.fulfill({json:{...session,user:{...session.user,id:'changed-identity'}}}));release();
 await expect(page.getByRole('alert').filter({hasText:'访问权限或身份已变化'})).toBeVisible();expect(downloads).toBe(0);await expect(page.getByLabel('上传评价结果')).toHaveCount(0);
});
