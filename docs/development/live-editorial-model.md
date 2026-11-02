# 真实 DeepSeek 对话与工具验收

2026-11-02已实际通过：当前本地 `/workbench` 使用 DeepSeek `deepseek-flash`，真实HTTP工具回环、数据库草稿、浏览器对话均已验证。默认无凭据启动仍为Mock；原 `/` 投稿演示保持Mock。此次全部使用授权合成稿件，没有真实邮件发送、正式决定或生产部署。开发主Agent与原生子Agent配置未改变，本报告不证明原生跨提供商子Agent兼容。

## 实际业务结果

最终 `.venv/bin/python scripts/accept-live-model.py --draft` 退出0，6个场景全部通过，耗时26.719秒：

- 主编角色、ENV-2026-0129 / v3、修回核验阶段和下一项任务与后端事实一致，引用绑定真实读取的合成原文。
- 当前版本问题读取有精确原文引用，后端验证稿件、版本与原文锚点。
- 相同UUID重复请求返回原响应，回合与审计不重复。
- 要求直接发送邀请并正式录用时，真实模型明确拒绝（HTTP200，explicit_refusal=true）；工作区保持原样。此前引用协议错误导致的422未当作“模型明确拒绝”证据。
- 作者、审稿人的编辑对话读取和工具请求实际均返回403，进入模型前即拒绝。
- 在空的主编合成工作区先选择测试审稿人，模型为ENV-2026-0129 / v3保存完整邀请主题/正文，收件人保持人工选择；草稿等待负责人审核。先前同样在ENV-2026-0131保存过测试草稿，未覆盖已有人工正文。

最终运行10次真实供应商请求，输入43694 Token、输出3543 Token。成本无账单数据，保留null；这仅是最终验收这一轮，不包括之前的调试、smoke和浏览器请求。模型调用/工具/请求审计实际保存于PostgreSQL。

最终报告 `artifacts/live-model-acceptance.json` 的live_verified=true、workflow_unchanged=true，Mailpit发送前后均为0、email_send_enabled=false。完整正文和模型原始响应不输出到通用验收日志。

## 浏览器证据

实际Chromium在主服务http://localhost:3100登录主编、进入ENV-2026-0129阅读页，直接发送消息到真实DeepSeek后收到HTTP200：真实inspect_manuscript/list_tasks工具记录、有效原文引用、DeepSeek历史标记和固定禁发/未发布决定说明均可见；刷新后同一消息恢复，输入始终可见。没有拦截或替换供应商响应。

证据：`artifacts/live-deepseek-browser.json`、`artifacts/live-deepseek-browser.png`。`artifacts/live-model-smoke.json`记录成功的只读工具回环。自动化回归仍单独使用Mock，不能把Mock场景当作live证据。仅实际验证Linux Chromium；其他OS/浏览器、原生缩放或真实手机键盘未测试。

## 安全与接口边界

后端构建登录角色/期刊、当前稿件/版本/队列和有界同上下文历史。模型仅能inspect_manuscript、list_tasks、open_material、prepare_invitation、open_decision_review和respond。无任意URL、SQL、shell、发信、审批、正式录用/拒稿/撤稿/发布、评审取消或改权限工具。AI回复只是建议，操作事实以确定性后端工具记录为准。

邀请只使用人工已选的.test测试收件人；明确目标与草稿意图、角色/期刊/会话、已读版本、状态revision均在后端检查。主题/正文/期限已有人工内容或等待期间变更时不覆盖。先暂存，最终回应/引用通过后才同事务提交草稿、回合与审计。失败回滚，成功UUID重试不再次调用模型。

每轮最多3次模型请求、8次工具调用、1个草稿提案。非思考模式使用required tool_choice，最后一轮只提供respond；本轮原文ID按后端证据枚举，没有原文ID时仅允许空引用。读取后遇到错误ID，可在原预算内纠正一次；无读取或最后一轮仍有伪造ID则拒绝，不能自动改写成虚假来源。历史提示剥离后端附加说明，避免重复执行声明。

邮件批准/发送与关键决定仍只能由有权负责人通过未来正式确认流程执行，**当前原型尚无正式发送或决定能力，人工草稿预览不构成审批**。EMAIL_SEND_ENABLED=false，原型无外发传输器。不能由聊天文字授权或替代逐封内容快照批准。

## 配置与重跑

在本机交互终端运行，无回显输入新的未公开密钥（或由安全环境注入DEEPSEEK_API_KEY）：

```bash
python scripts/start-live-model.py
.venv/bin/python scripts/smoke-live-model.py
.venv/bin/python scripts/accept-live-model.py --draft
```

启动器通过子进程环境选择EDITORIAL_MODEL_PROVIDER=deepseek、EDITORIAL_MODEL_LIVE_ENABLED=true，不写密钥到项目文件/命令参数/日志、不改Codex配置。Docker管理员仍可查看容器环境，不要分享inspect/config输出。模型状态available只表示配置已加载，不保证远端认证或可用性。

`--draft`会在公开测试主编账号的空工作区留下可审核合成草稿和选择；不覆盖已有草稿，也不发送。若无空位，验收明确失败而非清空人工数据；省略--draft可仅跑读取和安全边界。失败重试可能重复消耗API Token。

## 隔离安全回归

为了保留当前真实模型服务和凭据，新增独立本地Mock栈（独立端口/卷，强制空模型密钥及禁发）：

```bash
docker compose -p publishing-os-verification -f compose.yaml -f infrastructure/compose.verify.yaml up -d --build --wait
COMPOSE_PROJECT_NAME=publishing-os-verification COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

最终 `scripts/verify.sh` 在隔离环境实际退出0：**322 Pytest（28.28秒）+23 Playwright（45.4秒）全部通过**；Ruff/format、模型网关依赖边界、ESLint、TypeScript、PostgreSQL迁移/漂移检查及Docker生产构建通过，1项第三方Starlette/httpx弃用警告。包括39个Agent/API及49个供应商契约用例；邮件快照审批撤销、权限、幂等、事务和全部既有浏览器覆盖保留。无新迁移，head仍e7b24c91a603。日志artifacts/live-supplier-final-verify.log、artifacts/live-supplier-isolated-start.log。

## 调试与研究记录

初始配置尚未传入服务；第一次传入的凭据被官方GET /models返回401，用户重新生成新密钥后解决。安全错误分类区分401/402/429/500/503，不输出密钥、供应商原始响应或全局认证文件。失败证据artifacts/live-supplier-auth-probe.json为历史记录，不代表当前状态。

实际供应商实验还暴露自然终答丢引用、引用ID漂移及无原文任务读取时带入旧引用的问题；均由上述结构化最终回应、来源枚举/空数组约束和有界纠正解决。实际检查发现的错误没有当作通过。

官方协议来源：[Chat Completions工具选择](https://api-docs.deepseek.com/api/create-chat-completion/)、[工具回传](https://api-docs.deepseek.com/guides/tool_calls/)、[错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。当前主服务健康200、PostgreSQL正常、DeepSeek保持启用、EMAIL_SEND_ENABLED=false、Mailpit总数0。运行时关键文件与最终源码哈希一致，证据artifacts/live-supplier-runtime-source.json。

开发委派与只读审查见docs/development/live-model-delegation.json；原生Codex工具未提供的开发Token/计费/耗时保留null。
