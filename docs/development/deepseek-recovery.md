# 真实出版对话：恢复与端到端验收

2026-11-03。上一轮真实失败已保留，不覆盖为成功：请求ec75d599-ac2e-4ac7-afa1-d7ebf161e559在第二次推理读超时，另一次30秒进程内实验收到503。本轮先不改代码重跑，真实6/6通过（29.155秒），证明故障具有间歇性；无法从本机证明供应商内部容量原因。

## 实际修复

Model Gateway改为可取消AsyncClient，保持同步worker接口；新领域从请求入口共用60秒期限，旧工作台55秒，网络空闲read为30秒，其余5秒。小型空白保活不再延长期限。3轮/8工具及单次2048输出上限保留，每回合跨轮最多额外重试一次推理（500/502/503/504或网络/超时），短退避、相同输入字节、重试前重新授权；不重放整个chat或工具。没有Mock回退。

独立审查发现apply等锁后可能迟到保存，已补apply后与成功返回前期限检查；实际候选已在事务内应用后再过期的测试证明整体回滚。数据库锁等待与COMMIT本身不宣称硬取消。负责人声明、投稿/评审/决定/校样最终确认和邮件权限均未扩大。逐次推理遥测保留成功/失败与未知成本，不保存供应商正文、提示、密钥或会话。

## 真实主服务与浏览器

`./scripts/start.sh`实际更新成功，安全保留本项目API容器的live环境，没有写密钥文件/日志、改变主模型或全局配置。主库head为12e06b9c4f53。运行容器内三个关键模块的SHA256与当前源码一致（gateway/editorial.py、domain/chat.py、editorial_agent.py），见artifacts/live-publishing-runtime-evidence.json。

修复后真实API验收 **6/6通过，35.178秒**，没有拦截供应商响应：

| 场景 | 实际结果 |
| --- | --- |
| 创建本人私人稿件 | create_draft真实落库，保持author_draft |
| 资料整理 | propose_intake保存未核实候选，不代勾声明 |
| 实际文件 | read_current_file读出随机SYNTHETIC-LIVE标记，并引用对应文件 |
| 当前稿件与角色 | 回答编号/作者/步骤，查询不修改；相同UUID重放返回完全相同响应 |
| 准备审核 | prepare_review只创建pending快照，不确认投稿 |
| 越权发信/录用请求 | 业务完全不变；未分派审稿人的详情与chat均404 |

报告artifacts/live-publishing-recovery-final.json。测试账号自行填写声明属于明确的合成测试表单设置，不是模型生成声明。

真实Chromium通过页面登录主服务、选中POS-2026-000003，向当前稿件提问；读取实际文件/角色/步骤并引用（7.402秒），危险发信/录用请求不改状态（3.460秒）。刷新后实际回应恢复，独立审核页对话仍可见，核对框未勾选、提交按钮disabled、proposal仍pending，确认POST为0；pageerror为0，Mailpit前后0。未拦截API或模型响应。报告artifacts/live-publishing-browser.json，截图live-publishing-browser.png与live-publishing-browser-review.png。第一轮同类浏览器验收也通过，后因截图抓到审核页历史加载中，补等待并重跑；保留first报告。

本轮四份报告合计16个成功chat回合、31次实际供应商请求，返回usage输入156185/输出8835 Token，费用未知null；这是所列报告的范围，包含未改代码基线及两次浏览器，不是整个项目历史总量。本轮这些真实请求没有503或超时；503恢复及取消的确定性验证来自另列离线故障注入，不混淆两种证据。

数据库按请求逐项查得每回合1个Turn/Receipt/完成审计，audit与turn遥测一致。两篇验收稿仍author_draft、未冻结，HumanConfirmation/EditorialDecision/PublicationPreview均为0。升级前23用户、49稿件、1437审计、95旧对话ID全部保留，现25用户、51稿件、1486审计、95旧对话；新稿都是明确合成验收数据。未真实发送邮件、作出关键决定或生产部署。

## 自动回归与复跑

新增12项传输测试及14项API故障注入，保留旧测试与原断言意图：503/timeout恢复不重复工具、跨轮重试额度、401/402/429不重试、保活/慢headers取消、权限撤销阻止重传、人工修改优先、耗尽失败与apply后超时完整回滚。目标集合65传输、37新领域旧回归、47旧工作台/失败审计、14新增API均通过；最终完整scripts/verify.sh实际退出0：**835 Pytest（371.58秒）+35 Playwright（1.4m）**，静态/边界/研究门禁、数据库迁移/漂移、ESLint/TypeScript、浏览器脚本语法及准确前后端构建启动通过。日志artifacts/deepseek-recovery-full-verify.log，1项既有第三方warning。

```bash
./scripts/start.sh
.venv/bin/python scripts/accept-live-publishing.py --live --synthetic-writes --output artifacts/live-publishing-recovery-final.json
node scripts/accept-live-publishing-browser.mjs --live
```

API命令会新建一篇私人合成稿件与pending提案，浏览器使用该报告；会消耗真实模型API，均不调用最终确认或发信。没有新安全环境凭据时保持Mock继续离线建设。已有供应商若持续不可用，有限恢复后明确失败并回滚，不承诺供应商永不出现503。

官方依据与取舍见 [研究记录](../research/deepseek-recovery.md)。原生跨提供商Codex子Agent仍未验证成功；此前实际通过的独立安全API开发委派另见v01-deepseek-delegation.md，不由本次产品回环推断兼容。
