# 开发状态

更新：2026-11-02。首个编辑初筛纵向原型已实现并通过本地自动化验收。未真实发信、未生产部署、未更改主模型或全局 Codex 配置。

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

本期是本地、单期刊、合成数据原型，非生产系统。模型只支持既定测试指令；完整评审/修回/决定/制作/出版尚未实现，OJS/Janeway 只有适配契约。邮件审批为后端不变量，没有真实邀请 UI、附件存储或发送 outbox。收到新密钥后仍需真实 DeepSeek 工具循环验证，不能从本地 Mock 探针推断兼容性。后续顺序见 ROADMAP.md：完整状态/权限 → Agent/多模型 → 邮件审批/邀请 → 评审/决定/修回 → 制作/发布 → 评测/部署/加固。

## 恢复入口

读 AGENTS.md、README.md、ARCHITECTURE.md、SECURITY.md、DECISIONS.md 和 specs/001-editorial-intake.md。Web 3100 / API 8100 / DB 55432 / Mailpit 8025；不要操作已有 8000 端口模型服务，不读全局认证、不真实发信、不自动生产部署。运行 `./scripts/start.sh`，安装测试环境 `./scripts/setup.sh`，验证 `./scripts/verify.sh`。
