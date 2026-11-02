# 真实模型编辑对话接入

本轮将 `/workbench` 对话接到独立 DeepSeek 传输和受控工具循环。默认仍为 Mock；当前没有新的安全环境凭据，**真实 DeepSeek 供应商调用尚未验证**。离线 HTTP 契约、PostgreSQL 集成和浏览器 UI 契约各有不同证据，不能相互冒充。

## 本地启用

在本机交互终端运行：

```bash
python scripts/start-live-model.py
```

在无回显提示中输入**新生成且未在聊天中公开**的密钥。若安全环境已注入 `DEEPSEEK_API_KEY`，脚本直接使用该变量。不要把密钥放入命令参数、聊天、代码、文档或日志。脚本通过子进程环境启用 `EDITORIAL_MODEL_PROVIDER=deepseek` 和 `EDITORIAL_MODEL_LIVE_ENABLED=true`，不写入文件、不改全局 Codex 配置。Docker 容器环境由本机 Docker 管理员可见；不要把 `docker inspect` 或 `docker compose config` 的输出用于日志/分享。

打开 http://localhost:3100/workbench ，模型标签应显示 DeepSeek。模型状态接口只检查配置，不能证明 API Key 有效、账户余额充足或供应商在线。缺配置时界面显示“未就绪”，可检查配置；不会假装 Mock 成功。运行以下只读合成稿件工具回环验证：

```bash
.venv/bin/python scripts/smoke-live-model.py
```

它通过真实本地登录与对话 API 提问，要求 DeepSeek 回合包含真实工具执行记录且无草稿写入，结果写 `artifacts/live-model-smoke.json`。只有 `live_verified=true` 才证明真实供应商工具回环通过；失败报告不输出原始模型正文、密钥或密码。该操作只增加私有对话与审计，不发送邮件。

恢复本地模拟：取消对应环境变量后运行 `./scripts/start.sh`（默认Mock）；在同一 shell 中配置的变量也需清除。`/` 原始投稿创建链维持原先 Mock，不因新工作台配置改变。主Agent、Codex子Agent和开发委派模型配置均未改变；产品运行时模型与开发助手分离。

## 上下文与工具

后端构建真实登录角色、期刊、选中合成稿件/版本、队列条件和授权目标；带上最多8轮中相同完整上下文的最近约6000字符历史。跨用户/期刊/其他稿件上下文、密码、cookie、密钥、其他人的草稿不会进入提示。来源数据始终是现有合成fixture，不把真实模型等同于真实论文或完整业务。文章/历史/模型输出均视为不可信数据。

- `inspect_manuscript`：真实读取授权合成摘要、正文分节、问题原文、候选人与评审轮次，按需返回服务器引用ID。
- `list_tasks`：在当前授权范围检索任务、产生右栏筛选。
- `open_material`：打开稿件材料。
- `prepare_invitation`：仅对用户明确要求的一篇稿件、人工已选审稿人准备私有信件。模型不能设置收件人；保留人工主题/正文/期限，拒绝未知/多稿歧义、否定或仅查询请求。先读取版本依据，再暂存模型文案，整轮成功才锁定并写入。阅读后的revision发生变化则不保存旧结果。
- `open_decision_review`：打开中性决定草稿页，结果仍由负责人选择/审核；不发布决定。
- `respond`：建议文字和已返回的引用ID。引用从后端原文生成，模型不能提交任意锚点或伪造来源。

至多3次模型请求、8次工具调用、1个草稿提案；网络超时与响应大小受限。未知工具/字段、角色/会话/期刊在等待期间变化、越权目标、伪造引用及预算耗尽都拒绝。草稿/回合/执行审计同事务提交；失败不留下半成品。相同UUID成功回执直接重放；失败后的重试可能再次消耗供应商Token。API费用未知则为null，不编造成本。

## 负责人确认

邮件发送、邮件批准、录用/拒稿/撤稿/公开出版、取消评审与权限变更均没有Agent工具。`EMAIL_SEND_ENABLED=false`，原型无真实邮件传输器。模型文字不能作为批准依据；每条真实模型回复包含后端固定的“本轮未发送邮件、未发布正式决定”以及可展开工具执行记录。邀请/决定仍在右侧独立材料中供负责人检查，聊天不构成正式确认。完整阶段审核与逐封邮件审批UI仍属后续开发，不能把当前草稿预览说成正式审批已上线。

真实模型每条历史消息单独保存供应商标记；切换当前配置不会把旧Mock消息改标为DeepSeek。模型错误不回显供应商原文，私有对话正文只在授权会话表中保存；通用审计只记录工具名/状态、请求ID、Token/耗时和错误码。

## 验证记录

最终实际 `./scripts/start.sh` 和 `./scripts/verify.sh` 退出0：**316 Pytest（27.91秒）+23 Playwright（49.8秒）全部通过**。新增47个离线传输契约、35个PostgreSQL工具循环/安全集成、7个启动器密钥边界测试；浏览器新增2个拦截HTTP响应的UI契约用例，全部既有场景保留。Ruff/format、依赖边界、ESLint、TypeScript、PostgreSQL迁移/漂移和Docker生产构建通过，无新迁移，head仍e7b24c91a603。1项第三方Starlette/httpx弃用警告。日志artifacts/live-model-final-verify.log、artifacts/live-model-start.log。最终本地健康接口200，editorial_model=mock、PostgreSQL正常、email_send_enabled=false；Mailpit捕获总数0。

阶段实际发现UI测试的alert定位包含Next路由播报器，改为限定编辑对话区域后全量通过，未删减断言。源码检测artifacts/live-model-design-audit.json为[]，不等于全面可访问性认证。Linux Chromium桌面/窄屏/CSS200回归已运行，其他浏览器/OS/原生缩放/手机键盘未实测。

只读smoke已实际运行并以2退出：artifacts/live-model-smoke.json中live_verified=false、error_code=fresh_live_model_configuration_required；这是缺凭据证据，不是供应商成功。界面/协议的假HTTP回环不冒称真实DeepSeek调用。测试默认隔离环境密钥，完整verify在浏览器前检查Mock服务，避免误消费真实模型账户。

真实调用阻塞原因：未提供新的安全环境凭据；聊天中公开的旧密钥未使用。官方接口/模型和工具回传依据见 `docs/research/editorial-model-provider.md`。后续凭据就绪后按上面的只读smoke完成最终供应商验收，再扩展正式角色与业务工具，不放宽发信或关键决定权限。

委派记录：docs/development/live-model-delegation.json。传输实现由隔离目录所有权的Codex助手交付，主Agent集成/编写工具权限和事务；助手再做只读代码复核，发现的目标与否定指令问题由主Agent修复并加入回归。工具未提供的开发Token/计费/耗时不作估算。
