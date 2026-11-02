import {test, expect} from "@playwright/test";

// UI contract tests use an intercepted model status/turn. They do not prove a live supplier call.
const modelURL = "**/api/editorial-demo/chat/model";
const chatURL = "**/api/editorial-demo/chat";
const status = {provider:"deepseek",model:"deepseek-flash",available:true,synthetic_only:true,email_send_enabled:false,human_confirmation_required:["email_send","final_decision"]};
const context = {scope:"case",case_id:"demo-001",version:"v3",view:"read",stage:"all",query:"",today_only:false};
async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("邮箱",{exact:true}).fill("editor@publishing.test");
  await page.getByLabel("密码",{exact:true}).fill("EditorDemo2026!");
  await page.getByRole("button",{name:"进入工作台"}).click();
  await expect(page.getByRole("navigation",{name:"工作空间"})).toBeVisible();
  await page.goto("/workbench?view=read&case=demo-001");
  await expect(page.getByRole("textbox",{name:"对话消息",exact:true})).toBeVisible();
}

test("真实模型标签、执行记录、历史 Mock 标签与右侧材料联动",async({page})=>{
  await page.route(modelURL,route=>route.fulfill({json:status}));
  const old = {id:"old-mock-turn",role:"assistant",provider:"mock",content:"先前的模拟结果",created_at:new Date().toISOString(),context,references:[]};
  await page.route(chatURL,async route=>{
    if(route.request().method()==="GET") return route.fulfill({json:{provider:"deepseek",messages:[old]}});
    const input=route.request().postDataJSON();
    return route.fulfill({json:{request_id:input.request_id,provider:"deepseek",state_changed:false,messages:[
      {id:"new-user-turn",role:"user",provider:"deepseek",content:input.message,context:input.context,created_at:new Date().toISOString(),references:[]},
      {id:"new-live-turn",role:"assistant",provider:"deepseek",content:"[AI 建议 · 合成稿件] 请负责人检查修回证据。",context:input.context,created_at:new Date().toISOString(),references:[],action:{type:"navigate",case_id:"demo-001",view:"revision",prepare:"decision"},tool_receipts:[{tool:"inspect_manuscript",status:"read",case_id:"demo-001"},{tool:"open_decision_review",status:"human_review_required",case_id:"demo-001"}]}
    ]}});
  });
  await login(page);
  await expect(page.getByRole("status",{name:"当前模型"})).toHaveText("DeepSeek · 合成数据");
  await expect(page.locator('[data-message-id="old-mock-turn"]')).toContainText("Mock");
  await page.getByRole("textbox",{name:"对话消息",exact:true}).fill("请打开负责人审核材料");
  await page.getByRole("button",{name:"发送消息",exact:true}).click();
  const reply=page.locator('[data-message-id="new-live-turn"]');
  await expect(reply).toContainText("DeepSeek · AI 建议");
  await reply.getByText("工具执行记录",{exact:true}).click();
  await expect(reply).toContainText("读取稿件材料：已读取");
  await expect(reply).toContainText("等待人工审核");
  await expect(reply).toContainText("聊天不构成批准");
  await expect(page).toHaveURL(/view=revision/);
  await expect(page.getByRole("textbox",{name:"对话消息",exact:true})).toBeInViewport({ratio:0.95});
});

test("缺凭据不会假装 Mock 成功，检查配置后可继续；供应商失败保留原请求重试",async({page})=>{
  let ready=false;
  await page.route(modelURL,route=>route.fulfill({json:{...status,available:ready,...(!ready?{error_code:"fresh_deepseek_key_required"}:{})}}));
  let sent=0;
  const requestIds:string[]=[];
  await page.route(chatURL,async route=>{
    if(route.request().method()==="GET") return route.fulfill({json:{provider:"deepseek",messages:[]}});
    const input=route.request().postDataJSON();
    requestIds.push(input.request_id);sent++;
    if(sent===1) return route.fulfill({status:503,json:{detail:"safe failure"}});
    return route.fulfill({json:{request_id:input.request_id,provider:"deepseek",state_changed:false,messages:[{id:"recovered-live-turn",role:"assistant",provider:"deepseek",content:"[AI 建议 · 合成稿件] 已恢复查询。",context:input.context,created_at:new Date().toISOString(),references:[]}]}});
  });
  await login(page);
  await expect(page.getByRole("status",{name:"当前模型"})).toContainText("未就绪");
  await expect(page.getByRole("button",{name:"发送消息",exact:true})).toBeDisabled();
  await expect(page.getByText(/不会自动切换为 Mock/)).toBeVisible();
  expect(sent).toBe(0);
  ready=true;
  await page.getByRole("button",{name:"检查模型配置"}).click();
  await expect(page.getByRole("status",{name:"当前模型"})).toHaveText("DeepSeek · 合成数据");
  await page.getByRole("textbox",{name:"对话消息",exact:true}).fill("查询状态");
  await page.getByRole("button",{name:"发送消息",exact:true}).click();
  await expect(page.getByRole("region",{name:"编辑对话",exact:true}).getByRole("alert")).toContainText("真实模型尚未就绪或暂时不可用");
  await expect(page.getByRole("textbox",{name:"对话消息",exact:true})).toHaveValue("查询状态");
  await page.getByRole("button",{name:"重试消息",exact:true}).click();
  await expect(page.locator('[data-message-id="recovered-live-turn"]')).toContainText("已恢复查询");
  expect(requestIds).toHaveLength(2);expect(requestIds[0]).toBe(requestIds[1]);
});
