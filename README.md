# Publishing OS

以对话与 AI Agent 为入口的科研期刊出版操作系统原型。首条业务链真实运行于 PostgreSQL：登录 → 对话创建合成测试稿件 → 提交并分派编辑初筛 → 状态、待办、对话、审计持久化 → 刷新恢复。

**当前模型为明确标记的 Mock；真实邮件始终禁用；不包含生产部署。**

当前外观依据用户提供的最新 Hermes 工作台截图：浅灰侧栏、白色对话区、细蓝色选中线与底部输入框。参考证据和适配取舍见 [DESIGN.md](DESIGN.md)。原样遵循 AGENTS.md 中的精简标签规则；四个设计技能的来源、分工和安装记录见 [设计技能](docs/development/design-skills.md)，本轮审查与限制见 [设计验收](docs/development/design-acceptance.md)。

## 一键启动

前提：Docker Engine + Docker Compose 可用，首次构建可访问公开镜像/依赖仓库。项目默认仅本机可访问，使用公开的合成演示账号。

```bash
./scripts/start.sh
```

脚本启动 PostgreSQL、Mailpit、FastAPI 和 Next.js，等待健康检查；API 启动时自动执行 Alembic 迁移与幂等 demo bootstrap。不需要手工创建表或复制密钥。

- [编辑工作台](http://localhost:3100)
- [API 文档](http://localhost:8100/docs)
- [Mailpit 本地捕获界面](http://localhost:8025)（原型没有外发传输器，通常为空）

端口为 3100 / 8100 / 55432 / 8025，均绑定 loopback。已有 8000 端口服务不受影响。

停止：`./scripts/stop.sh`。该命令保留 PostgreSQL 卷；再次启动仍保留数据。不要使用 `docker compose down -v`，除非明确要删除全部本项目数据。

## 测试账号与演示

| 角色 | 邮箱 | 密码 | 当前权限 |
| --- | --- | --- | --- |
| 编辑 | editor@publishing.test | EditorDemo2026! | 创建测试稿件、分派初筛、查看本期刊稿件/审计 |
| 作者 | author@publishing.test | AuthorDemo2026! | 仅查看本人稿件，不能执行编辑工具 |
| 审稿人 | reviewer@publishing.test | ReviewerDemo2026! | 尚无分派，不能读取稿件或执行编辑工具 |
| 主编 | chief@publishing.test | ChiefDemo2026! | 本期与编辑相同；正式决定工具尚未开放 |

1. 用编辑账号登录。
2. 输入 **“创建一篇测试稿件，并交给编辑初筛。”** 并发送，也可使用可操作的快捷指令。
3. 查看标记为“模拟结果”的执行回复，以及真实稿件的“编辑初筛”状态、待处理初筛任务和负责人。
4. 刷新浏览器，在“稿件管理”和“审计记录”中检查同一稿件 ID。
5. 退出后用作者/审稿人登录；尝试相同指令得到服务端 403，无法越权创建。

Mock 只模拟意图识别，稿件/任务/状态/审计不是前端假数据。期刊和四类用户由 bootstrap 真实写入；命令为当前编辑创建稿件与任务。投稿工具当前支持一条明确指令，其他输入会保存解释而不创建稿件。

## 常驻对话与四页工作材料

编辑或主编登录后点击“我的工作”，或打开 [任务工作台](http://localhost:3100/workbench)。左侧是任务导航，中间是始终可见的主体对话，右侧随上下文切换四类工作材料。对话历史、未发送输入和上下文跨页保留；四页使用同一组**明确标记的合成稿件**；筛选视图、阅读位置、候选选择、版本笔记、问题核验和邀请/决定草稿真实保存至当前用户的 PostgreSQL 工作区，原型真实投稿链仍在 `/`。

1. 在中间对话询问“这篇稿件目前的状态和下一步是什么？”；或将对话范围切换到“当前工作队列”，输入“今天有哪些待初筛任务？”。模拟查询形成真实可操作的材料列表。选中稿件后上下文自动对应；历史消息仍标明原稿件与版本。
2. 阅读 ENV-2026-0129 的中英文长稿，切换三份版本、通过问题跳转原文与修回位置；查看图表/计算公式/附件/参考文献/历史，调整字号、面板宽度或专注阅读。
3. 在“审稿人选择”筛选、连续预览并比较候选；选择后准备.test收件人的邀请，编辑主题、期限、正文并查看完整草稿快照。
4. 在“修回核验与决定”查看两轮问题、回复和原文差异，保存人工核验、内部笔记；选择中性的拟定结果、编辑决定信并查看草稿。进行中的评审任务保持不变。
5. 直接对话“列出当前版本尚未解决的问题，并给出原文依据”“准备邀请草稿”“协助准备决定草稿”，可打开来源和对应工作材料。邀请须先人工选人；已有人工正文不覆盖。模拟检查工具仍在对话下方展开，可取消/重试、改写和处置结果。

默认浅色，可选深色/跟随系统。原始文件是可下载的合成文本，与重排版段落一致；不冒称PDF/DOCX解析。候选档案、论文、既往流程与分析均为合成场景，不是真实履历或学术结论。没有真实模型、发信、正式决定、任务取消或权限变更能力。作者/审稿人目前无此编辑演示工作台访问权。

设计规范见 [DESIGN.md](DESIGN.md)，接口/数据边界见 [spec004](specs/004-workbench-contract.md)，完整验收、截图与未验证平台见 [本轮交付记录](docs/development/workbench-delivery.md)。工作台采用隔离的草稿/视图表和私有对话回合表，尚未实现spec003的完整出版数据库与作者辅助投稿。常驻对话契约见 [spec005](specs/005-conversation-first-workbench.md)，最新截图/验证/模拟边界见 [常驻对话交付记录](docs/development/conversation-first-delivery.md)。

## 会话与邮箱

侧栏支持真实新建/搜索/切换对话，各会话消息独立持久化，刷新恢复选中会话。桌面可收起侧栏，手机使用可关闭抽屉；稿件详情按需打开。

“邮件”支持自建 SMTP、Gmail、Outlook 配置保存、只读连接/身份验证、断开与重新绑定。本地 Mailpit 预设无需凭据且已真实验证。云账号需服务器端 OAuth 访问令牌；当前没有 OAuth 授权跳转、自动刷新、收件箱或发信能力。保存配置不表示已连接，验证成功也不授予发送权限。

配置步骤、凭据环境引用、期刊所有权与 SMTP 允许列表见 [邮箱绑定指南](docs/development/mail-binding.md)，空模板为 `infrastructure/mail.env.example`。真实 Gmail/Outlook 账号未提供凭据，因此未实测，不声称已经连接。

## 自动验证与本地开发

运行测试工具需 Node.js 22、Python 3.12+、uv 和浏览器系统依赖。先启动服务，再安装项目隔离测试环境：

```bash
./scripts/setup.sh
# Linux 首次若缺 Chromium 系统依赖：npx playwright install-deps chromium
./scripts/verify.sh
```

验证包含 Ruff、模型依赖边界、真实 PostgreSQL 迁移/漂移、Pytest、ESLint、TypeScript、Compose 中的 Next.js 生产构建和真实 API 的 Playwright。测试不会删除演示数据；普通 Pytest 使用外部事务回滚，并发测试只保留唯一命名合成数据，E2E 会保留新建演示稿件。

证据写入 `artifacts/pytest.xml`、`artifacts/playwright-report/index.html`、`artifacts/playwright-results/`；浏览器截图为 `artifacts/hermes-desktop-chat.png`、`artifacts/hermes-mobile-chat.png` 与 `artifacts/mail-settings.png`。最新实际执行结果见 [PROGRESS.md](PROGRESS.md)。CI 定义在 `.github/workflows/ci.yml`，本次交付不声称远端 GitHub Actions 已执行。

分项命令：

```bash
.venv/bin/pytest -q
.venv/bin/alembic check
npm run lint
npm run typecheck
docker compose build web
npm run test:e2e
.venv/bin/python scripts/check-boundaries.py
```

当前宿主环境 `npm run build` 的 PostCSS 内部工作进程端口被沙箱 EPERM 拒绝；验收执行与启动一致的 `docker compose build web`，没有跳过构建。

热更新开发：停止 Compose 中的 Web/API（`docker compose stop web api`），运行 `./scripts/dev.sh`；该脚本继续使用同一 PostgreSQL，启动本地 API 与 Next 开发服务，退出时停止这两个进程。`DATABASE_URL` 可通过环境覆盖；默认是本机项目数据库。只允许 PostgreSQL，不使用 SQLite 替代验收。

## 模型协作

主模型配置保持不变。DeepSeek 目标为 **DeepSeek-V4.1-Flash-1017 / deepseek-flash**。当前无新密钥：真实 DeepSeek 调用 **0 次**，原生跨提供商子 Agent **未验证**。已通过隔离 Codex CLI → loopback 假 Responses 服务 → 真实无副作用 shell 工具 → 工具结果回传实验；这不代表真实 DeepSeek 通过。

可测试替代路径：安全 API 委派器，默认 Mock，草稿仅写入 UUID 隔离目录，由主 Agent 审查集成，不执行生成代码。支持 research/api/react/tests/documentation。只在明确加 `--live` 后从可信环境读取新 `DEEPSEEK_API_KEY`；不要将密钥放进命令参数、Git 或日志。

```bash
.venv/bin/python -m packages.model_gateway.delegate --kind research --task 'Inspect a synthetic editorial API boundary'
.venv/bin/python -m packages.model_gateway.report /tmp/publishing-delegations
.venv/bin/python evals/model_codex_probe.py
```

在本地交互终端运行下面的命令，可使用**新的、未在聊天中公开过的**密钥执行一个具体的 UI 审查子任务。脚本优先读取 DEEPSEEK_API_KEY 环境变量；未设置时无回显提示输入，只传给独立子进程，不改变主 Codex 模型，也不把密钥写入文件。结果与遥测写入 gitignored `artifacts/delegations/<UUID>/`，等待 Lead 审查集成。这是独立 API 协作，不能冒称原生跨供应商 Subagent 已验证。

```bash
./scripts/delegate-deepseek.sh
```

逐任务记录成功、Token、成本、耗时与返工；未知成本为 null。Ollama/vLLM 预留显式 opt-in、仅 loopback 接口。真实模型接入产品还需要后续集成与评测，当前 Web 原型固定 Mock，避免环境密钥意外导致稿件外传。详见 [DeepSeek 协作验证报告](docs/research/deepseek.md)。

## 后续数据库与产品规划

三栏“我的工作 / 对话协作 / 稿件进度”、分阶段初审、AI辅助信息整理与独立负责人审核页已形成详细规格，见 [数据库与工作流规划](specs/003-editorial-workflow-and-assisted-intake.md)。这份规格尚未实施，不代表当前原型已具备完整投稿或评审能力。下一次优先交付数据/待办基础与作者辅助投稿的一条真实链。

## 项目地图

- `apps/web`：现代紧凑对话工作台、稿件详情、审计、运行时同源代理。
- `apps/api/publishing`：Domain、Runtime、Workflow、Policy、Action、Audit 与可撤销登录会话。
- `packages/mail_adapters`：只读 SMTP/Gmail/Outlook 探测；`packages/model_gateway`：模型边界、安全委派、遥测；`packages/integrations`：未来 OJS/Janeway 契约。
- `infrastructure`：Dockerfiles 与 Alembic 迁移；`specs`：功能/API 契约；`tests`/`evals`：安全与回归验证。
- [PRODUCT.md](PRODUCT.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[SECURITY.md](SECURITY.md)、[DECISIONS.md](DECISIONS.md)、[ROADMAP.md](ROADMAP.md)、[研究与来源](docs/research/landscape.md)。

安全约束由代码强制：确定性权限/状态、请求幂等、事务审计、审计不可改写、审批快照修订失效、真实邮件无传输器。完整评审、决策、制作和公开出版属于下一阶段，不能从本地原型推断生产能力。
