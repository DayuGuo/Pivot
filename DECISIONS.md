# 架构决策记录

日期：2026-11-02。官方研究与来源见 docs/research/landscape.md、docs/research/deepseek.md。

## ADR-001：先实现一个纵向切片

选择编辑初筛合成稿件链，使用规格与自动化验收贯穿浏览器、业务、数据和审计。用户明确拒绝静态展示交付。完整出版业务按 ROADMAP 递进，不预造全部功能。

## ADR-002：独立确定性出版核心

使用 Next.js + FastAPI + SQLAlchemy + PostgreSQL，Alembic 管迁移，Docker Compose 启动。依据 OJS/Janeway 分离角色、稿件阶段和编辑任务；现阶段不继承其数据库或自动发信逻辑。模型仅提议工具，后端执行白名单、策略与状态机。

## ADR-003：有界 Agent 与安全模型隔离

本期产品固定 Mock，并在 UI/返回消息中标记。真实模型协议保留在独立委派 CLI，需要显式 --live、新环境 Key、合成/公开上下文。没有密钥时继续 Mock；不读取旧密钥、不修改全局 Codex 配置或主模型。原生子 Agent 的 provider 继承限制、DeepSeek Responses 兼容性及独立协议探针见专门报告，不能据 Mock 实验声称真实 DeepSeek 已通过。

## ADR-004：事务、可重试与审计

单条命令的实体、两次状态转换、分派、消息、审计、回执同事务提交。PostgreSQL advisory lock + actor/request 唯一约束防并发重复；输入 digest 防错误复用。审计禁止 SQL 更新/删除/清空，重大操作无 Agent 能力。拒绝在回滚后单独审计。

## ADR-005：安全会话与本地演示

采用可撤销随机数据库会话与 HttpOnly cookie、CSRF，不在 localStorage 保存认证信息。角色按期刊成员关系与记录归属校验。只提供本地合成账号，Compose 端口只绑定 loopback。已有服务占用 8000，选 API 8100、Web 3100，PostgreSQL 55432，Mailpit 8025，避免影响现有工作负载。

## ADR-006：邮件始终禁发

用户逐封人类审批要求高于模型便利性。实现草稿/不可变审批快照/修订失效/禁发入口与测试，不提供 SMTP 外发传输器。Mailpit 是本地测试设施，当前无发信业务；后续正式传输必须先具备 outbox、幂等与不确定结果恢复，不能仅靠环境开关上线。

## ADR-007：可恢复开发 Harness

短 AGENTS 入口 + 产品/架构/安全/决策/进度/规格，脚本化启动和验证，CI 保存证据。依据 Spec Kit 的可追踪工件、Anthropic 增量开发与浏览器验证、OpenAI 仓库知识源模式。子任务按目录隔离；API 权限和集成由主 Agent 管理。默认主模型未更改，DeepSeek 草稿输出使用隔离 UUID 目录。

## ADR-008：实时代理而非构建时 API URL

Next.js 使用运行时 API route 代理，避免构建时 rewrite 将 localhost 固化进容器；代理明确保留会话 cookie/CSRF，设置 no-store 与请求超时。页面、Playwright 与 HTTP 客户端共用真实 API。

## ADR-009：以当前 Hermes 官网视觉为准

用户将视觉参考改为新版 Hermes Agent，并强调当前官网与旧版不同。采用 2026-11-02 实时官网截图、当前官网 Desktop 预览和最新发布信息，弃用标记 v0.16 的旧 PR 截图作为视觉权威。官网蓝色 #0000f2 与蓝白对比用于产品外框和登录；聊天阅读区保持安静。字体使用 OFL 的 Barlow Condensed 5.3.0 自托管，不复制 Hermes 商业字体、标识和插图。具体证据、适配选择及限制见 DESIGN.md。

用户的精简文案规则原样加入 AGENTS.md，并配置四技能分工：Frontend Design、UI/UX Pro Max、Impeccable、Web Design Guidelines。通用技能建议不替代已明确的产品与安全要求。

## ADR-010：新密钥只进入独立委派进程

聊天中提供的密钥按已有“不使用已暴露密钥”约束不使用；不复制密钥到仓库或日志。新增无回显本地启动器和具体 UI 审查任务文件，真实 DeepSeek 仍需新的环境密钥。这个执行器独立于原生 Codex 子 Agent，结果是待主 Agent 审查的草稿，不把 Mock 或独立 API 协作冒称原生跨提供商 Subagent。
