# 工程 Harness 与期刊业务调研

调研日期：2026-11-02。以下为已实际打开的官方文档和官方源码；它们说明可借鉴的模式，不等于本项目已经实现或验证相应产品的兼容性。具体交付证据以 PROGRESS.md 为准。

## 1. OpenAI：目标、可恢复上下文和产品内 Agent

[Codex Goals 官方指南](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)将 Goal 定义为有明确完成条件与验证面的持久目标。[Codex 开放 Harness 官方说明，2026-08-19](https://developers.openai.com/blog/codex-as-a-platform)区分 Agent 循环与应用拥有的业务规则、上下文、工具和审批：CLI 适合有界后台任务，SDK 适合程序化会话，app-server 面向持续对话和事件。开源 Harness 不代表模型服务或第三方协议兼容。

[Harness Engineering 实践，2026-02-11](https://openai.com/index/harness-engineering/)强调：让仓库成为知识记录源，AGENTS.md 充当短入口；让 UI、日志、测试可被 Agent 检查；通过机械化检查约束架构边界。该文的高自治案例依赖特定工程环境，不能直接推广为所有项目的能力保证。

**本项目取舍：**首个纵向功能采用小型、有界 Agent Runtime。模型只能提出已登记工具，Action Gateway 执行权限校验和事务；不让模型直接执行 SQL。AGENTS.md 作为入口，产品、架构、决策、进度文档保存上下文；启动、验证和验收结果保存在仓库中。后续可评估 app-server/MCP，但其引入不能替代后端权限与审计。

原生子 Agent 与 DeepSeek 的实际验证另见 [DeepSeek 调研报告](deepseek.md)，不从通用多 Agent 文档推断跨提供商兼容。

## 2. GitHub Spec Kit：将意图连到验证证据

[Spec Kit 官方文档](https://github.github.com/spec-kit/)（页面标记更新于 2026-09-28）给出 Specify → Plan → Tasks → Implement → Converge 流程，各阶段生成可传递的 Markdown 工件。[Agentic SDD 参考](https://github.github.com/spec-kit/reference/agentic-sdd.html)说明跨 spec、plan、tasks 的只读一致性检查。

**本项目取舍：**采用规格、接口契约、验收用例与执行结果的可追溯关系，在 `specs/001-editorial-intake.md` 固定第一条业务链。不为最小原型引入所有模板、扩展或代码生成命令，不改写全局 Agent 配置。后续引入 Specify CLI 前先验证它对现有目录和指令文件的影响。

## 3. Anthropic：长周期开发的可恢复工件和独立评估

[长周期 Agent Harness 实践](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)建议区分首次初始化和后续增量编码，保留功能列表、启动脚本、进度与 Git 历史；必须实际运行浏览器端到端验证，避免只凭代码或 curl 宣布完成。[2026-03-24 后续实践](https://www.anthropic.com/research/harness-design-long-running-apps)尝试 planner、generator、evaluator 分工，并指出自我评价的偏乐观风险及重审 Harness 复杂度的必要性。

**本项目取舍：**先验收一条功能链，每次修复后重跑相关检查；以 Pytest、Playwright 和数据库断言提供独立于模型判断的证据。任务委派按目录隔离，主 Agent 集成与审查权限逻辑。无需预先搭建复杂的自治集群；只有真实失败表明需要时才扩展编排。

## 4. OJS 3.5：业务阶段、参与者和决定权限

PKP 文档已重组，旧的 `/learning-ojs/en/` 链接在本次工具中无法访问；实际读取了 PKP 官方仓库中标记为 **OJS 3.5** 的当前文档：

- [编辑工作流总览](https://github.com/pkp/pkp-docs/tree/main/learning-ojs/editorial-workflow/en)：投稿 → 审稿 → 文字编辑 → 制作，再进入出版及出版后版本管理。
- [投稿与初筛](https://raw.githubusercontent.com/pkp/pkp-docs/main/learning-ojs/editorial-workflow/en/submission.md)：新稿进入投稿阶段，分派编辑后可初筛决定或送审；分派时可区分最终决定与建议权限，以及出版信息编辑权。
- [审稿阶段](https://raw.githubusercontent.com/pkp/pkp-docs/main/learning-ojs/editorial-workflow/en/review.md)：审稿轮次、审稿人邀请/响应/完成期限、匿名策略、修回与编辑决定各自有状态；文件匿名化还需编辑检查。
- [用户与角色](https://raw.githubusercontent.com/pkp/pkp-docs/main/learning-ojs/journal-managers/en/users.md)：角色关联期刊、阶段和权限级别；作者能投稿、审稿人只访问获分派阶段，助理权限随阶段限制。OJS 3.5 对用户信息编辑和角色邀请加入了更严格的边界。

**本项目取舍：**业务核心独立于 OJS，首期只实现 draft → submitted → screening，与待办编辑任务关联。后续状态机应将稿件阶段、编辑任务、审稿轮次与具体决定拆开；不能用一个自由文本 status 承载全部含义。权限必须同时检查期刊成员关系、角色、记录归属与分派。仅有“编辑”角色不足以获得所有期刊的数据访问权。OJS 中自动邮件通知的现成行为不能直接复制，Publishing OS 对真实邮件要求逐封绑定内容审批。

## 5. Janeway：分派、角色作用域与信息可见性

本次实际读取官方 `latest` 文档，页面显示 **Janeway 1.7.5**，未将其等同于最新已发布软件版本：

- [编辑初筛与审稿](https://janeway.readthedocs.io/en/latest/editor/review.html)：投稿先进入未分派队列，编辑分派处理人后进入审稿或作出决定；作者兼编辑进入本人稿件审稿存在冲突检查。审稿人先响应邀请，评审完成后对作者的可见性另行控制。
- [用户和角色](https://janeway.readthedocs.io/en/latest/manager/users/)：编辑管理期刊范围内账户与角色，staff 具有出版机构层面的额外权限；编辑、审稿、文字编辑、制作、校样等任务有不同角色。
- [工作流指南](https://janeway.readthedocs.io/en/v1.7.2/workflow.html)和 [Typesetting 插件](https://janeway.readthedocs.io/en/latest/editor/typesetting.html)：文字编辑、制作、校样及出版前步骤可作为独立工作单元；排版产物可包括 PDF、HTML 和 JATS XML。

**本项目取舍：**记录稿件 author_id 与任务 assignee_id，避免将用户全局角色当成无限授权；评审内容与作者信息需独立的可见性策略。保留未来适配器接口，通过外部 ID 映射、受控同步和契约测试连接 Janeway，不直接共享数据库表或声称开箱兼容。完整的利益冲突、多角色组合和匿名审稿策略属于后续阶段。

## 6. Craft Anything：有证据的检查与构建循环

“Craft Anything”在此明确对应 [ArtCraft 官方应用页](https://getartcraft.com/apps/craft-anything) 和 [storytold/craft-anything 官方仓库](https://github.com/storytold/craft-anything)，而不是名称近似的文档应用或 Create Anything 服务。官方描述为用真实检查工具研究软件，再构建、比较、修正；同一引擎可通过桌面、CLI 或 MCP 访问，并对超出规则的动作提供控制。

**本项目取舍：**借鉴“统一工具接口 + 可检查证据 + 重复验证”这一模式：Conversation UI 和自动测试都调用真实 API，不能用仅展示按钮或前端内存伪造业务结果。当前没有安装、运行或集成 Craft Anything，也不复用其代码；不存在对其工具数量、可用性或平台兼容的验证结论。

## 7. 合并后的架构约束

下列为依据上述资料及用户安全要求形成的项目设计判断，而非来源直接保证：

| 边界 | 确定性职责 | 模型可做的事 |
| --- | --- | --- |
| Publishing Domain Core / Workflow Engine | 实体关系、合法状态转换、任务分派规则 | 提议下一步工具 |
| Policy Engine | 期刊作用域、角色、记录归属、关键决定人类权限 | 解释校验结果，不能自行授权 |
| Action Gateway | 工具白名单、参数校验、事务、幂等、审批与失败处理 | 提交结构化调用 |
| Audit System | 行为人、目标、前后状态、请求关联与时间 | 读取被授权的摘要 |
| Model Gateway / Agent Runtime | 提供商隔离、超时、响应校验、遥测、有限循环 | Mock 或真实模型产出候选工具 |
| Conversation UI | 用户意图输入与真实状态显示、明确模拟标记 | 给出人可读执行反馈 |

第一期的验证面必须贯穿浏览器、API、PostgreSQL 与审计，并覆盖刷新恢复、角色拒绝、重复请求和邮件禁用。正式录用、拒稿、撤稿、公开出版与真实外发邮件不属于自主执行工具集。

未来 OJS/Janeway 适配接口应使用独立模块，将外部状态映射到内部命令，并通过相同 Action Gateway 执行。接口声明与真实集成验收必须分开记录。
