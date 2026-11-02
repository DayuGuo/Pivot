# 开发状态

## 活跃 Goal：OJS / Janeway 数据库研究与 v0.1 完整样本

2026-11-02 新 Goal 已建立，持续执行中，**尚未完成整个目标**。恢复先读 goals/publishing-v0.1.md、specs/007-* 和 docs/research/library/README.md。分支 codex/publishing-v01；旧版已验收基线354c930保留。

已实际归档 OJS3.5.0-6/其PKP固定gitlink 与 Janeway1.8.4 的官方源码/指南证据、字段表、许可/摘要；研究门禁验证39+35来源及18基线文件，59表/412字段与61模型/553字段为静态索引，非上游运行数据库导出。比较取舍见 docs/research/library/comparison/database-decisions.md。

A/B 已写入真实领域基础、13张规范化子表、作者/版本/实际UTF8文件、任务/分派/不可变提案与独立人工确认、同源对话工具及常驻三栏新路由 /publishing。迁移f8a12d4c6e90在独立55433数据库upgrade/check通过，24项随机schema迁移/回退/冻结约束重演通过；旧UUID/历史不变，真实新投稿出现后拒绝破坏性降级。C的CheckRun与09b73e6a1c22已编写、独立迁移试验中，尚未接通业务关口。

新A/B接口、文件安全与聊天测试已运行；基础全后端一轮426通过，随后安全/聊天聚焦35通过，最终完整验证仍待执行。浏览器首轮暴露旧并发测试给共享作者留下多期刊授权；已仅撤销隔离库4项Pytest临时授权、保留稿件/审计，并修复测试finally清理。其他修复：旧审计隐藏私人领域事件、准备/确认检查实际CAS字节、锁/模型等待后重新授权、人工默认值候选保护、聊天历史及重放访问依赖检查。对应回归继续运行。

A/B检查点最终完整 `scripts/verify.sh` 已实际退出0：**508 Pytest（40.41秒）+24 Playwright（含新增作者→编辑真实投稿链）通过**；研究门禁、Ruff/format、TypeScript/ESLint、PostgreSQL迁移/漂移与Docker生产构建均通过。日志 artifacts/v01-ab-checkpoint-verify.log。另四条独立数据库连接的相同人工确认重试只生成一条确认、一次修订和一项预审待办；24项基础迁移演练通过。已修下拉框标签语义、浏览器脚本的历史对象定位和登录等待；保留旧记录未清空数据库。此检查点仅证明A/B及C独立组件，不代表完整v0.1已完成。

当前主服务仍为此前真实模型版本，**新领域尚未部署至主库或进行真实供应商验收**。新代码在独立Mock验证栈18100/13100运行，上传用独立持久volume。新UI静态检查通过，浏览器交互和全量verify尚待最终证据。后续预审/送审/评审/修回/决定/制作/本地预览仍未实现；不得从已写表/页面推断已完成。邮件始终禁用，无生产部署。


更新：2026-11-02。首个编辑初筛纵向原型已实现并通过本地自动化验收。未真实发信、未生产部署、未更改主模型或全局 Codex 配置。

## 当前验证：真实DeepSeek对话与受控工具已通过

用户在本机安全配置有效密钥后，实际DeepSeek deepseek-flash模型回环成功。最终live验收6/6通过（26.719秒）：主编角色/ENV-2026-0129-v3状态与原文引用、问题依据、UUID响应/审计幂等、危险发信/正式录用指令明确拒绝且工作区不变、作者/审稿人403、私有邀请主题/正文真实保存与人工收件人保留。Mailpit前后0，正式状态未改变；未发信/未作关键决定。

实际Chromium主界面对话也使用真实DeepSeek，工具/引用/角色标记和刷新恢复通过；见artifacts/live-deepseek-browser.json/.png。最终live报告artifacts/live-model-acceptance.json：10次供应商请求、输入43694/输出3543Token，成本未知为null，仅该轮统计。先前401凭据已解决，历史失败未当作成功。

实际调用修复了自由终答丢引用与引用ID漂移：required工具选择、最终回合respond、后端来源枚举/无来源空数组、原预算内一次来源纠正；坏来源仍拒绝，草稿最终校验后才提交。独立代码复审通过；最终隔离 `scripts/verify.sh` 实际退出0：322 Pytest（28.28秒）+23 Playwright（45.4秒）、静态检查、迁移/漂移和生产构建通过，1项第三方弃用警告。日志artifacts/live-supplier-final-verify.log；无新迁移，head e7b24c91a603。配置/平台限制和运行命令见docs/development/live-editorial-model.md；当前运行时真实供应商验证不代表原生跨提供商Codex子Agent已验证。

## 当前更新：真实模型与安全工具循环

按spec006实现独立DeepSeek工作台adapter、角色/期刊/版本上下文、最多3轮/8工具/1草稿的真实工具协议。草稿整轮成功后才提交，等待期间复核人工修改和权限；来源ID、请求幂等、审计与Mock历史供应商标记保留。邮件批准/发送、重大决定均无Agent工具。安全本地启动器就绪，不落盘密钥。

以下为接入代码初次交付的历史证据；当时真实DeepSeek调用0、未提供新凭据。当前真实验收见上节，聊天公开的旧密钥未使用。最终 `./scripts/start.sh` 与 `./scripts/verify.sh` 退出0：**316 Pytest（27.91秒）+23 Playwright（49.8秒）通过**，Ruff/format、依赖边界、ESLint、TypeScript、迁移/漂移、Docker生产构建通过；1项第三方弃用警告。新增47离线传输、35真实PostgreSQL工具循环安全集成、7启动器测试及2浏览器UI契约场景；日志artifacts/live-model-final-verify.log。审查补强明确目标/否定指令、等待期间人工修改/撤权和固定执行边界。无新迁移，head仍e7b24c91a603。只读smoke实际退出2并记录live_verified=false/fresh_live_model_configuration_required，不把假HTTP回环冒称真实供应商验证。详细启用、平台限制及委派记录见docs/development/live-editorial-model.md和live-model-delegation.json。

## 最新用户修正：对话为主，材料随行

按spec005将原弹出助手改为四页常驻主体对话，左任务/中对话/右材料；自动白名单筛选与导航、真实私有聊天历史、当时上下文快照、原文引用和安全邀请/决定草稿准备已接入。新增回合表e7b24c91a603，旧真实投稿链保留。人工未保存内容有准备前同步及冲突候选恢复；纯查询不因未完表单阻断。

最终实际运行 `scripts/start.sh` 和 `scripts/verify.sh`：**227 Pytest（22.39秒）+21 Playwright（46.6秒）全部通过**，含45个聊天API用例及6个新增对话浏览器场景；Ruff/format、依赖边界、ESLint、TypeScript、PostgreSQL迁移/漂移、Docker生产构建通过。另13个工作台场景阶段复测通过（38.2秒）。日志artifacts/conversation-final-verify.log；迁移head e7b24c91a603。1项第三方Starlette/httpx弃用警告。实际修正CSS200输入/发送裁切、窄屏正文不足、人工草稿保存竞态和字体偏好恢复时序；20种页面布局检查正文与发送按钮实际可见区域。仅Linux Chromium及CSS缩放，未实测其他OS/浏览器/原生缩放/手机软键盘。交付与限制见docs/development/conversation-first-delivery.md，委派证据conversation-delegation.json；截图artifacts/conversation-*。

## 已完成Goal：任务工作台、长稿阅读、选人及修回核验

已读取用户目标文件goal-objective.md并按spec004增量开发。新路由/workbench保留原投稿/邮件链，四页共用6篇合成稿件，其中主案例3个版本、2轮修回、多审稿人、长中英文正文与历史。私有草稿、阅读位置、候选选择、核验、AI建议处置及常用视图经真实API/PostgreSQL保存；迁移c81b8c41b016只增加两个隔离状态表，未修改正式出版状态机。

所有指定参考的9个官方URL已实际读取，取舍见docs/research/workbench-design.md；统一规范已补入DESIGN。独立审查发现并修复版本阅读误删核验历史、失败笔记导航恢复及局部滚动引起外层空白；浏览器首轮暴露代理缺PATCH/PUT及下载头，现已补齐。原型不发送、不取消评审、不发布正式决定、不改变关键权限，模拟材料有明确披露。

最终 `scripts/start.sh` + `scripts/verify.sh` 实际退出0：**182 Pytest +15 Playwright**（原8+新7），Ruff/format、依赖边界、ESLint、TypeScript、迁移/漂移、Docker生产构建通过。日志artifacts/workbench-start.log、artifacts/workbench-final-verify.log；head c81b8c41b016；1项第三方Starlette/httpx弃用警告。段落级恢复、字体18下刷新定位和失败草稿经过无关保存后恢复均实际通过。12个四页桌面布局（1366/1440/1920）无横向溢出，主要主题文字色对表面最低5.55:1；实际Linux Chromium，含深色/系统、键盘、CSS200%与窄屏。其他OS/浏览器、原生工具栏缩放未实测。截图、来源、模拟/待接入项及精确审查范围见docs/development/workbench-delivery.md；委派记录workbench-delegation.json不可用Token/成本/耗时留null。不得把新界面推断成spec003完整业务已实现。

## 最新规划：数据库、三栏任务工作区与负责人审核

用户本轮要求已固化到 specs/003-editorial-workflow-and-assisted-intake.md：核心步骤与标签分层、逐关负责人、版本/作者/文件/分派/任务/检查/提案/确认/轮次实体、约束索引、并发幂等、角色待办排序、AI提取与缺项表单、独立审核页、历史迁移和分批验收。复核了现有models/workflow/policy，记录了单status、必填editor_id、单author_id、任务唯一键和单role的结构缺口。实际读取OJS/Janeway官方工作流资料，来源记录在规格末尾。

PRODUCT、ARCHITECTURE、SECURITY、DESIGN、DECISIONS与ROADMAP同步区分“后续设计”和“已运行能力”。本轮只更新规划文档，没有修改运行代码、数据库schema或权限，不声称三栏/作者辅助投稿/新审核页已实现。下一次优先A+B纵向切片；现有完整原型验收见下方。

本轮文档变更后已实际运行 `scripts/verify.sh` 并退出0：145 Pytest、8 Playwright、Ruff/ESLint/TypeScript、PostgreSQL迁移/漂移检查与Docker生产构建通过。日志 artifacts/workflow-planning-verify.log。这仅证明现有原型回归通过，不证明新规格中的后续功能已实现。

## 当前更新：截图工作台、真实会话与邮箱绑定

本节覆盖下方历史蓝色外框设计。视觉权威改为用户直接提供的 Hermes 工作台截图，详见 DESIGN.md 和 ADR-011。浅灰侧栏、白色对话阅读区、细蓝色选中线、底部输入框、可收起侧栏/手机抽屉均已实现；真实会话支持新建、搜索、切换、URL恢复和草稿隔离。历史消息已迁移到真实会话，回执保持旧请求重试兼容。

邮箱配置支持自建 SMTP、Gmail、Outlook，具备持久状态、验证、断开与重新绑定审计。凭据只读服务器专用环境变量，并校验期刊所有权。探测与发信分离，无发信能力。实际 Mailpit EHLO 验证通过，捕获消息总数为0；真实 Gmail/Outlook 和远程 SMTP 无授权凭据，未验证。OAuth consent/refresh 与收件箱尚未实现。

最终完整 `scripts/verify.sh` 退出0：**145 Pytest + 8 Playwright**，含56适配器用例及37新增会话/邮箱API用例；生产容器构建、Ruff、ESLint、TypeScript、迁移/漂移通过。实际 head 为 a99d14733f66，包含旧消息回填。日志 artifacts/final-screenshot-start.log、artifacts/final-screenshot-verify.log，JUnit artifacts/pytest.xml。Pytest有1项第三方 Starlette/httpx 弃用警告，不影响通过。

独立后端安全审查未发现需处理的实质问题。独立视觉审查确认布局与配色，要求统一实际中文字体；已增加自托管 Noto Sans SC Variable 5.3.1（OFL-1.1），最终截图复核对这项修复给出 scoped ship。Chromium CDP实际报告品牌、会话名、输入区使用 NotoSansSC-Thin 的自定义变量字体（isCustomFont=true）；不是从CSS声明推断。最终截图 artifacts/hermes-desktop-chat.png、artifacts/hermes-mobile-chat.png、artifacts/hermes-mobile-drawer.png、artifacts/mail-settings.png 和 artifacts/mail-setup-guide.png。没有真实云账号或DeepSeek供应商调用、邮件发送或生产部署。

## 后续界面与设计 Harness 更新

- 用户要求参考新版 Hermes Agent、与当前官网相近，明确排除旧版风格。已实际读取 2026-11-02 当前官网、官方桌面预览、源码设计文档和最新发布 v0.22.5；旧 v0.16 PR 截图不再作为视觉权威。当前官网的蓝白视觉被适配为蓝色产品外框/侧栏、安静阅读区、自托管 Barlow Condensed 字体；没有复制 Hermes 商标、商业字体或插画。证据与限制见 DESIGN.md。
- AGENTS.md 原样加入用户规则：Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining. 已删除重复标语、无用英文 eyebrow 和多余说明。
- Frontend Design、UI/UX Pro Max、Impeccable、Web Design Guidelines 四个技能已从官方上游安装至全局技能目录。UI/UX 数据库检索、Impeccable context 和检测器已实际运行；没有启用 hooks/live 自动应用或改写 Codex 全局配置。来源和内容校验见 docs/development/design-skills.md / .json。
- 新增可显隐的稿件上下文面板和响应式状态；独立 Codex 视觉审查发现的残余英文标签及手机面板显示不一致已修复，手机导航点击区域达到 44px。独立复查对列出的修复给出 scoped ship；验收范围与限制见 docs/development/design-acceptance.md。保留真实状态、角色、Mock 披露及邮件禁用提示。
- 最新完整验证：**52 个 Pytest（39 API + 13 模型/CLI）、5 个 Playwright**通过；Ruff、ESLint、TypeScript、Next.js 构建、PostgreSQL 迁移和漂移检查通过。日志 artifacts/hermes-verify.log，截图 artifacts/editorial-workspace.png、artifacts/hermes-login.png、artifacts/hermes-mobile.png。Impeccable 源码检测实际返回空数组；这不等于浏览器可访问性全面认证。
- DeepSeek 新增无回显本地启动器、具体的公开/合成 UI 审查任务文件、CLI --task-file 及 6 个边界测试。聊天中提供的凭据未使用、未写入文件或日志；没有新的环境凭据，因此真实供应商调用仍为 0，仍不可声称原生跨 provider 成功。

## 初始交付基线（4dfbc2d）

| 项目 | 实际结果 |
| --- | --- |
| 一键启动 | `./scripts/start.sh` 实际成功；PostgreSQL、Mailpit、FastAPI、Next.js 均 healthy |
| 真实数据库与迁移 | PostgreSQL 17；Alembic `0002_audit_guards (head)`；`alembic check` 无 schema 漂移 |
| 完整验证脚本 | `./scripts/verify.sh` 退出 0；日志 `artifacts/verify.log` |
| 后端与模型契约 | Pytest **46 passed**：39 个 API/业务/安全用例 + 7 个网关离线契约用例；JUnit `artifacts/pytest.xml` |
| 浏览器 | Playwright Chromium **4 passed**，运行于完整 Docker 产品；编辑登录/真实创建/刷新/审计/注销，作者与审稿人 403，错误密码，CSRF/跨站登录保护 |
| 静态检查 | Ruff check + format，模型依赖边界，ESLint 与 TypeScript 全通过 |
| 前端工件 | Next.js 生产构建通过（本机与 Docker）；清空本机 `.next` 后 `next typegen && tsc --noEmit` 也通过 |
| 生产依赖 | `npm audit --omit=dev` 为 0 vulnerabilities；开发工具链仍有 16 项 moderate 的 minimatch 传递依赖公告，未盲目执行破坏性降级 |
| 独立 Codex 协议实验 | CLI 0.165.0 + 隔离 CODEX_HOME + loopback 假 Responses 服务，2 次模型请求、真实无副作用 shell 工具执行及结果回传；`evals/model_probe_result.json` |
| 真实 DeepSeek | **0 次调用，未验证**：未提供新 DEEPSEEK_API_KEY；原生跨提供商 Subagent 也未建立可靠验证。已保留可测试的安全 API 委派器与报告 |
| 邮件安全 | 无 SMTP 外发传输器；默认 false，环境强行 true 仍返回 403。完整快照绑定、修订撤销、跨期刊拒绝及数据库不可篡改测试通过 |

浏览器报告：`artifacts/playwright-report/index.html`；截图：`artifacts/editorial-workspace.png` 和 `artifacts/editorial-intake.png`。测试证据为本机实际结果；GitHub Actions 工作流已定义，远端运行未触发，不声称远端 CI 已通过。

## 已完成实现

- 官方研究：OpenAI Goals/Subagents/Harness、Spec Kit、Anthropic 长周期 Harness、OJS、Janeway、Craft Anything、DeepSeek 官方集成，来源和取舍在 docs/research。
- 八个模块边界；Next.js/React/TypeScript/Tailwind、FastAPI、SQLAlchemy、真实 PostgreSQL、Alembic、Docker Compose。
- Bootstrap 真实写入期刊、四类用户、成员角色和审计；命令以事务完成稿件创建、draft → submitted → screening、编辑待办、对话、审计和幂等回执。
- 随机可撤销会话、scrypt、CSRF、期刊/角色/归属检查、数据库审计追加保护；四连接并发重复请求只创建一次，失败不留下部分稿件。
- UI 可操作登录、对话、快捷指令、稿件查看、审计、刷新与注销；明确 Mock 标记，无未实现业务假按钮。
- 安全模型 API 委派、UUID 隔离草稿、成功率/Token/成本/耗时/返工遥测；Mock 样本 1/1、0 Token/$0，未知真实成本保留 null；Ollama/vLLM 仅接口未实测。
- setup/dev/start/stop/verify、本地浏览器证据与 CI；Git 仓库保存可恢复的产品、架构、安全、决策、进度与规格。

## 本轮修复与审查

独立审查发现并修复：邮件禁发入口缺期刊检查、邮件快照类型约束不足；PostgreSQL JSON 比较改为 jsonb，保护触发器已实测。前端改用运行时 API 代理，避免构建时 localhost 固化；保留 Sec-Fetch-Site，使跨站登录防护经代理仍生效。浏览器测试定位器冲突已修复，并提高文字可读性。最终检查补齐 Next 冷启动 typegen 和开发脚本 npm 参数转发。

## 限制与下一步

本期是本地、单期刊、合成数据原型，非生产系统。原投稿链保持Mock；工作台真实模型工具回环已通过本地验收；完整评审/修回/决定/制作/出版尚未实现，OJS/Janeway 只有适配契约。邮件审批为后端不变量，没有真实邀请 UI、附件存储或发送 outbox。真实API运行时已验证，原生跨提供商Codex子Agent仍未验证；不能从产品API回环推断开发助手兼容性。后续顺序见 ROADMAP.md：完整状态/权限 → Agent/多模型 → 邮件审批/邀请 → 评审/决定/修回 → 制作/发布 → 评测/部署/加固。

## 恢复入口

读 AGENTS.md、README.md、ARCHITECTURE.md、SECURITY.md、DECISIONS.md 和 specs/001-editorial-intake.md。Web 3100 / API 8100 / DB 55432 / Mailpit 8025；不要操作已有 8000 端口模型服务，不读全局认证、不真实发信、不自动生产部署。运行 `./scripts/start.sh`，安装测试环境 `./scripts/setup.sh`，验证 `./scripts/verify.sh`。
