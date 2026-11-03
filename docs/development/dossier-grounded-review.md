# 资料区版本证据问答

本地功能，对应spec014。公网静态Demo保持展示用途。本轮的实际运行结果以PROGRESS.md和下列本机证据为准，不把Mock通过等同真实DeepSeek通过。

## 使用方式

`./scripts/start.sh`安全更新本机服务并保留已有模型选择。登录后打开`/library`选择本人资料，保存完整TXT/Markdown和作者元数据，再提问。服务端明确配置DeepSeek且凭据可用时走`deepseek-flash`；新环境默认Mock，真实启用沿用`scripts/start-live-model.py`，不在聊天或仓库保存密钥。真实失败不会静默变成Mock答案。

对话展示结论、实际读取覆盖、可点击的原文/作者字段引文及经核验的外部文献。每条引文绑定版本、内容digest、文件SHA256与Unicode范围；点击时重新鉴权和校验，可精确高亮，历史引用只能打开原来的版本，不覆盖当前未保存表单。旧rules历史继续标明未调用模型。

全文和全部作者元数据都建立本地分段索引；模型在预算内分页/检索所需片段，不把长稿悄悄截断后声称完整审阅。界面显示实际覆盖，无正文只按元数据作答；逐字定位只证明引用出处准确，不证明结论的科学正确性或语义支持，必须由编辑复核。

## 外部文献的可信范围

仅查询当前授权资料或用户问题已提供的DOI，固定请求Crossref官方端点，精确匹配后返回真实DOI/Crossref链接和书目信息。不允许模型编造URL、自由网页地址、另一篇未提供DOI或未经核验记录。状态verified_metadata仅表示书目匹配；本轮没有读取外部全文、认证ORCID人物或执行全网文献检索。核验失败不出“已核验”链接。

官方来源与公开DOI实连见`docs/research/dossier-sources.md`。固定端点、TLS、超时、字节上限、禁重定向及代理、异常JSON/HTML处理有独立协议测试。

## 权限与持久化

仅当前本刊editor/chief_editor且为资料录入者可访问。回合进入Action Gateway、幂等重放重新鉴权；只读模型工具无邮件、录用、拒稿、发表或资料确认。网络不持资料写锁，最终锁后复核原身份、版本、实际CAS字节；失效、超时或伪造引用回滚，不留部分成功。

不可变DossierAnswer保存结构化结论、引文、外部记录、覆盖和脱敏遥测，与人工DossierCheck分开。聊天不创建人工核对事实，模型回合不能推进正式出版状态。当前问题/材料和待发历史筛查疑似密钥，含密钥的旧规则问题不作为模型历史。异常诊断不记录提示、原始供应商错误或凭据。

## 可复现验收

完整回归使用隔离Mock栈，避免真实模型费用和主服务配置被覆盖：

```bash
COMPOSE_PROJECT_NAME=publishing-os-verification COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

只有本机主API明确使用真实DeepSeek后才运行：

```bash
.venv/bin/python scripts/accept-dossier-model.py --live
```

该命令创建全新合成资料，实测全文/作者问答、真实Crossref DOI、危险操作拒绝、新版本数字、幂等与刷新，并核对邮件/决定/人工确认计数不变。只支持本机HTTP API，数据库检查固定本机演示DB55432；不适用于线上默认账号或真实保密资料。报告在`artifacts/dossier-live-acceptance.json`，不读取模型密钥、不给网页外发，不部署。

最终完整回归实际退出0：996 Pytest（387.65秒）+59 Playwright（1.8m），所有静态/迁移/构建检查通过。新51项chat、82项外部协议及完整迁移回退均通过。真实DeepSeek API4/4：全文/作者、外部DOI、危险操作零变更、新版数字，分别3.228/6.369/6.717/2.989秒。实际Chromium另完成从输入到引用高亮、刷新与375px检查（点击发送至定位/刷新/窄屏检查共2.904秒），没有确认/邮件/决定请求；随后重启API/Web，同会话恢复全部7条成功回合与原文件/版本/引文，仍未人工核对。

首轮真实HTTP成功但终答参数被严格拒绝，未写入部分业务；现允许已读来源后最多一次参数/引文纠正，不增加3轮/8工具总预算、不放宽最终验证。后续真实回合实际观察到超量引用/结论混入URL，已在预算内纠正。脱敏诊断只保留固定类型与已知字段位置，不含原始输入或供应商响应。

真实测量包含失败和验收脚本重跑：18次provider attempts全部HTTP成功，7条成功业务回合/1条失败；输入38,724、输出3,667 tokens，费用null待账单对账。不能把这当作真实供应商503恢复实验。浏览器脚本对同名引用与重复DOI链接的定位曾修正，多出的真实调用已包含在统计中。

本地证据：artifacts/grounded-full-verify-final.log、dossier-live-acceptance.json、dossier-live-browser.json、dossier-live-restart.json、dossier-live-telemetry-summary.json；未复制保密资料或密钥。main服务已更新，DeepSeek配置保留，公网Demo未更新。真实验收用合成短稿；长稿全文尾检索与预算由自动测试验证，实际读取范围始终可见。

补充SQL合同实际在隔离外层回滚事务执行：引用kind为NULL/未知值均以23514拒绝，有Answer历史的14a downgrade明确拒绝；证据artifacts/dossier-answer-sql-extra.json，没有留下测试业务数据。
