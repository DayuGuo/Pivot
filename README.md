# Publishing OS

以对话与 AI Agent 为入口的科研期刊出版操作系统原型。首条业务链真实运行于 PostgreSQL：登录 → 对话创建合成测试稿件 → 提交并分派编辑初筛 → 状态、待办、对话、审计持久化 → 刷新恢复。

**当前模型为明确标记的 Mock；真实邮件始终禁用；不包含生产部署。**

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

Mock 只模拟意图识别，稿件/任务/状态/审计不是前端假数据。期刊和四类用户由 bootstrap 真实写入；命令为当前编辑创建稿件与任务。当前支持一条明确指令，其他输入会保存解释而不创建稿件。

## 自动验证与本地开发

运行测试工具需 Node.js 22、Python 3.12+、uv 和浏览器系统依赖。先启动服务，再安装项目隔离测试环境：

```bash
./scripts/setup.sh
# Linux 首次若缺 Chromium 系统依赖：npx playwright install-deps chromium
./scripts/verify.sh
```

验证包含 Ruff、模型依赖边界、真实 PostgreSQL 迁移/漂移、Pytest、ESLint、TypeScript、Next.js 生产构建和真实 API 的 Playwright。测试不会删除演示数据；普通 Pytest 使用外部事务回滚，并发测试只保留唯一命名合成数据，E2E 会保留新建演示稿件。

证据写入 `artifacts/pytest.xml`、`artifacts/playwright-report/index.html`、`artifacts/playwright-results/`；浏览器截图为 `artifacts/editorial-workspace.png` 与 `artifacts/editorial-intake.png`。最新实际执行结果见 [PROGRESS.md](PROGRESS.md)。CI 定义在 `.github/workflows/ci.yml`，本次交付不声称远端 GitHub Actions 已执行。

分项命令：

```bash
.venv/bin/pytest -q
.venv/bin/alembic check
npm run lint
npm run typecheck
npm run build
npm run test:e2e
.venv/bin/python scripts/check-boundaries.py
```

热更新开发：停止 Compose 中的 Web/API（`docker compose stop web api`），运行 `./scripts/dev.sh`；该脚本继续使用同一 PostgreSQL，启动本地 API 与 Next 开发服务，退出时停止这两个进程。`DATABASE_URL` 可通过环境覆盖；默认是本机项目数据库。只允许 PostgreSQL，不使用 SQLite 替代验收。

## 模型协作

主模型配置保持不变。DeepSeek 目标为 **DeepSeek-V4.1-Flash-1017 / deepseek-flash**。当前无新密钥：真实 DeepSeek 调用 **0 次**，原生跨提供商子 Agent **未验证**。已通过隔离 Codex CLI → loopback 假 Responses 服务 → 真实无副作用 shell 工具 → 工具结果回传实验；这不代表真实 DeepSeek 通过。

可测试替代路径：安全 API 委派器，默认 Mock，草稿仅写入 UUID 隔离目录，由主 Agent 审查集成，不执行生成代码。支持 research/api/react/tests/documentation。只在明确加 `--live` 后从可信环境读取新 `DEEPSEEK_API_KEY`；不要将密钥放进命令参数、Git 或日志。

```bash
.venv/bin/python -m packages.model_gateway.delegate --kind research --task 'Inspect a synthetic editorial API boundary'
.venv/bin/python -m packages.model_gateway.report /tmp/publishing-delegations
.venv/bin/python evals/model_codex_probe.py
```

逐任务记录成功、Token、成本、耗时与返工；未知成本为 null。Ollama/vLLM 预留显式 opt-in、仅 loopback 接口。真实模型接入产品还需要后续集成与评测，当前 Web 原型固定 Mock，避免环境密钥意外导致稿件外传。详见 [DeepSeek 协作验证报告](docs/research/deepseek.md)。

## 项目地图

- `apps/web`：现代紧凑对话工作台、稿件详情、审计、运行时同源代理。
- `apps/api/publishing`：Domain、Runtime、Workflow、Policy、Action、Audit 与可撤销登录会话。
- `packages/model_gateway`：模型边界、安全委派、遥测；`packages/integrations`：未来 OJS/Janeway 契约。
- `infrastructure`：Dockerfiles 与 Alembic 迁移；`specs`：功能/API 契约；`tests`/`evals`：安全与回归验证。
- [PRODUCT.md](PRODUCT.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[SECURITY.md](SECURITY.md)、[DECISIONS.md](DECISIONS.md)、[ROADMAP.md](ROADMAP.md)、[研究与来源](docs/research/landscape.md)。

安全约束由代码强制：确定性权限/状态、请求幂等、事务审计、审计不可改写、审批快照修订失效、真实邮件无传输器。完整评审、决策、制作和公开出版属于下一阶段，不能从本地原型推断生产能力。
