# 当前 Publishing OS 的 v0.1 差距评估

评估日期：2026-11-02。评估方式为本地源码、迁移与测试定义静态核对，基线commit `354c930aca91634a6c1f0bb000a9415ac0226880`。本辅助任务没有访问数据库、启动/停止服务、运行测试、查看环境密钥或全局认证，也没有修改应用代码。当前父Agent可能继续开发；事实限定于manifest记录的源码指纹。

本目录只评估当前系统，不冒充已完成OJS/Janeway字段研究；上游证据由相邻研究目录提供。以下“建议”均为待实现，不是现有能力。

## 已有基础与关键断层

当前基础可复用：真实PostgreSQL/Alembic、随机会话+CSRF、scrypt密码、事务审计、防重复请求、内容快照邮件审批不变量、禁发、私有对话历史、DeepSeek结构化工具边界、常驻主体对话。现有322个后端/协议及23个浏览器用例通过的证据来自PROGRESS；本次仅阅读测试，没有重新运行。

关键断层是两个不同的数据体系：

1. 正式旧原型以 `manuscripts` / `editorial_tasks` 实现编辑代建合成稿件，只有draft→submitted→screening。
2. `/workbench` 从 `packages/editorial_demo/dataset.json` 读取6篇固定合成稿件，版本、作者、轮次、候选、问题、附件正文与历史均来自fixture。数据库只保存每用户的草稿/阅读偏好、检索视图和对话。

因此，“真实模型已读取/保存”只证明真实模型读取合成资料并真实保存私有工作记录；不证明已经有作者投稿、正式版本、评审分派、共享进度、逐关确认或完整出版链。不能把 `editorial_demo_states.content` 直接升格为正式出版数据库。

## 精确差距矩阵

| 领域 | 当前源码事实 | v0.1需要的业务事实 | 最小可行改动 |
|---|---|---|---|
| 期刊 | `Journal`仅id/name | 固定一刊也需投稿编号、文章类型、政策快照 | 期刊配置/类型可少量固定配置；编号在事务内分配，journal+number唯一 |
| 用户角色 | `Membership`同user+journal唯一、单role；`get_actor`按user取首个membership | 确定性工作期刊、角色能力、稿件分派/所有权、利益冲突 | 会话绑定工作期刊；新领域授权查询显式过滤journal。首版可用独立测试账号单角色，但禁止假设未来多membership时`.first()`安全 |
| 投稿 | `Manuscript.author_id`和`editor_id`必填，仅title/status/created_at | 作者可建准备稿，提交前尚无责任编辑 | 允许未分派编辑；author_id留为旧兼容投影，新增创建者/版本/阶段/修订号 |
| 状态 | `workflow.TRANSITIONS`只定义draft→submitted→screening | 关口、负责人、阻塞原因、退回/修回循环、终局与制作 | 明确阶段枚举+步骤实例+任务；模型无直接status setter |
| 版本/作者 | 无版本、作者顺序、机构、ORCID、通讯作者快照实体 | 提交/修回冻结版本，作者资料变更不改历史 | manuscript_versions + author_snapshots；身份关联与署名资料分离 |
| 文件 | fixture内保存合成文本，无真实上传与对象权限 | 原稿/匿名稿/回复信/报告/校样可追踪内容 | file_objects + version_files；hash/size/type/用途/可见性；下载每次授权，不接受任意路径 |
| 作者AI填报 | 现有创建工具仅编辑/主编且指定固定合成作者 | 作者先输入散乱信息，AI候选字段，后端缺项校验，独立确认 | form_drafts保存来源/不确定项；后端schema；声明由人勾选；不可复用编辑代建工具绕过身份 |
| 我的工作 | `EditorialTask`只有稿件/assignee/kind/status，稿件+kind唯一；workbench任务是假定fixture字段 | 真实可执行待办、期限/优先级、循环、负责人和等待项 | 新work_items以step实例唯一，不破坏旧表；角色可见待办/计数同一授权查询 |
| 分段初筛 | 无检查报告或放行记录 | 完整性、相似度报告复核、材料筛选、主编范围、责任编辑质量分别确认 | check_runs绑定版本/hash；人工相似度报告上传与确认，未接查重器明确“未自动检测” |
| 编辑分派 | 编辑在旧create_and_assign时自分派，不能改派 | 主编明确指定责任编辑，保留改派历史 | assignments有效期记录，结束旧分派并创建新分派，旧proposal失效 |
| 审稿邀请 | `CaseState.invitation`是每用户单份私有信件；候选为fixture | 每轮每审稿人的邀请、期限、接受/拒绝、冲突声明 | review_rounds/invitations/assignments；本期站内通知/邀请箱，不依赖真实邮件 |
| 评审报告 | 无真实报告实体、审稿人被整体403 | 仅分派轮次/版本可读，作者可见意见与编辑私密意见分离，提交人确认 | review_reports冻结最终版，草稿用form_drafts；API/文件/模型上下文均匿名投影 |
| 修回 | demo仅核验固定before/after，不能上传新版本 | 作者上传新版本、回复信，版本/报告关联与下一轮 | 新版本，不覆盖旧文件/报告；旧确认不能放行新内容 |
| 决定 | demo允许个人保存拟定outcome；正式状态机拒绝录用/拒稿 | 主编/授权负责人审核不可变决定快照后确认；通知分离 | editorial_decisions + action_proposals/human_confirmations；确认不进Agent表 |
| 制作/校样 | 只有fixture生产阶段，无数据动作 | accepted版本→制作包→作者校样→本地预览 | production_packages + proof任务/确认 + publication_previews；认证本地预览不等于互联网发布 |
| 审计/幂等 | DB审计追加保护、旧命令回执、chat私有UUID回执已有 | 新动作同样原子提交且拒绝/冲突可追踪 | 复用审计；新领域回执独立命名空间，不改旧request摘要语义 |
| 邮件 | 核心函数有不可变快照批准、修订撤销、send一律403；绑定是只读验证 | 保持默认false，正式业务/邮件审批独立 | 站内邀请贯通首版；后续邮件outbox再开任务。当前不开放真实SMTP/Graph/Gmail发送 |
| 对话 | 编辑/主编专用demoChatContext，allowed()/target()读取fixture | 各角色只见本人的真实任务/材料，动作对应真实对象 | 用新的领域context repository和投影；无需把旧fixture接口的Case形状硬塞成真实对象 |

## 建议的首版边界

单期刊、五组独立测试角色（作者/编辑部或责任编辑/主编/审稿人/出版人员），一篇从头创建的合成稿件、一名审稿人、一轮正式评审、一次作者修回与复核即可构成完整可操作样本。模型提供候选/建议/草稿；人负责每个业务关口。暂不做多刊管理、复杂多编辑联合签署、自动外部查重、DOI注册、生产公开发布或任意Workflow DSL。

单角色账号是首版规模限制，不应阻止同人兼作者时的利益冲突检查。可通过“版本作者linked_user_id/稿件访问关系包含当前用户”拒绝其作为决定人；未来再扩展MembershipRole集合。出版人员若新增角色，不要把旧`EDITOR_ROLES`扩大到所有演示/审计接口以求方便。

数据库按可运行切片建表，不先创建全量空表。详见[领域模型和迁移建议](schema-and-migration.md)、[权限与验收矩阵](policy-and-acceptance.md)。

## 必须保留的行为

- 现有manuscript UUID、旧Conversation/Message/CommandReceipt响应、邮件审批/禁发约束、追加审计和demo私有历史。
- 历史`screening`明确为legacy_screening，不补造查重通过、人类批准或主编决策。
- 当前真实模型容器凭据不因运行默认Mock回归栈被覆盖；使用`infrastructure/compose.verify.yaml`独立栈。
- 主体对话跨页面常驻；左侧只呈现真实“我的可执行/待确认/等待他人”事项；右侧从同一领域投影显示当前步骤/负责人/版本/阻塞与时间线。
- 没有实际操作的能力不放假按钮；相似度报告未接服务时可上传人工报告并明确来源，不能生成虚假的“查重率”。

## 当前证据入口

完整相对路径、源码SHA-256、行号锚点和数据库类字段静态清单见`manifest.json`、`inventory.json`。本报告没有运行验证，不把父Agent先前的322/23结果当作本辅助任务执行结果。
