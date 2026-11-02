# Publishing OS 数据库决策：把成熟出版经验变成可验证约束

日期：2026-11-02。依据 [OJS 研究](../ojs/README.md)、[Janeway 研究](../janeway/README.md)、[现有系统基线](../current-system/README.md) 和 [spec007 数据契约](../../../../specs/007-data-contract.md)。这份文件描述设计与预期验收，**不是新功能已经实现或测试通过的报告**。[机器可读映射](source-to-implementation.json) 给出每个字段组的具体上游表/类/字段、源文件、项目新增部分和验收目标；基础14类现已绑定实际源码与 `f8a12d4c6e90` 迁移；新增 CheckRun 绑定 `09b73e6a1c22` 并完成临时 schema 组件测试。绑定不是整条工作流已完成接线的声明。

研究固定 OJS 3.5.0-6 / `0f2de4ff3f399a65dbe5c24c035529c0ff9bc976`，以及该版本真实 gitlink 对应 PKP `c4c0aa8c5293254ad253544aea230b1b607d5249`；Janeway v1.8.4 / `e24b23bd112ff7ca08097620d8a31041a25f9d26`。OJS 表索引来自选定安装迁移，Janeway 来自模型 AST；都不是已执行迁移后的完整数据库导出。不能把“字段存在”和“数据库已有此约束”混同。

## 跨来源决定

| 决策 | 成熟系统中可观察的事实 | 我们采用什么 | 明确拒绝什么与如何验收 |
| --- | --- | --- | --- |
| DB01 稳定身份与版本 | OJS `submissions` 指向 `current_publication_id`，`publications` 有 `submission_id/version`；Janeway `Article` 稳定，`FrozenAuthor` 保留作者快照 | 保持原 Manuscript UUID，独立 Workflow 当前投影和不可变 ManuscriptVersion | 不把 OJS publication 直接等同投稿身份，也不把修回当新稿；验证同 UUID 多版、历史不变 |
| DB02 阶段、步骤与工作分开 | OJS stage、review_round、review_assignment 分离；Janeway Article.stage、ReviewRound、Task 各有状态/时间 | 主阶段回答“进展到哪”；StepRun 保留每次关口；WorkItem 回答“我今天做什么”；以后 ReviewRound 绑定本轮文件 | 不用一个 status 或任意标签包含所有事实；退回重做增加 cycle，不重置历史 |
| DB03 作者和账号分离 | OJS `authors.publication_id/email/seq`；Janeway `FrozenAuthor.author` 可空且 frozen_email/frozen_orcid | 版本署名、顺序、机构/贡献、通讯作者与账号分开；linked_user 仅身份线索 | 不从邮箱或署名自动授予权限；账号变更不改已冻结作者 |
| DB04 授权须到对象 | OJS context/user_groups/stage_assignments、recommend_only；Janeway AccountRole 期刊用户角色唯一且允许多角色 | 期刊成员 + 本稿有效分派 + 阶段 + COI 的后端策略，撤销分派立即生效 | 不以 editor 标签自动访问全刊，不准作者自审；跨刊/未分派/利益冲突直接拒绝 |
| DB05 文件版本与可见性 | OJS `files` 与 `submission_files`、revision/round files 分层；Janeway File.privacy、review_round.review_files | blob 不覆盖、实际 SHA/长度检查、VersionFile 固定用途/可见性、未来轮次固定盲审文件集 | 不复制 Janeway 普通整数 article_id；不虚称 UTF8 检查是 AV/PDF；冻结后替换附件必须失败 |
| DB06 草稿不是批准 | Janeway DecisionDraft 区别 editor_decision；OJS decision Repository 按类型/阶段校验 | AI 提取→有来源候选→独立审核页→责任人确认不可变快照，摘要绑定版本/内容/附件/政策 | 人类确认和失效规则是本项目更严格要求，不假称上游同等具备；聊天/AI 不能最终决定或发信 |
| DB07 用数据库守底线 | OJS 版号没有 install UNIQUE；review_form_responses_unique 实为普通 index；Janeway Task 泛型目标有误完成警告 | compound FK 保证同稿/同刊；partial UNIQUE 保证活跃分派；冻结触发器阻止直接 SQL 破坏 | 不凭索引名字推测唯一性，不只依赖 Python 验证；直接 SQL/并发/删除历史要失败 |
| DB08 回执、审计与对话 | OJS event_log 与 edit_decisions；Janeway WorkflowLog 留时间/责任人 | Action Gateway 的幂等回执 + 同事务审计；每回合保留经过权限过滤的上下文 | 上游日志不是我们的回执。网络超时重试不能重复推进；失败不能留下虚假成功 |
| DB09 分片扩展 | 两系统都有审稿/修回/制作/出版；Janeway 现代 typesetting 与历史 production 并存 | A/B 先真实作者 intake/任务/确认/对话；后片独立 ReviewRound、邀请/报告、RevisionRequest、CheckRun、制作与发布门 | 不一开始创建全部空表；不同时混用 Janeway 新旧制作生命周期 |
| DB10 材料是证据 | OJS GPLv3、Janeway AGPLv3；Janeway 指南 CC BY4.0；OJS 指南许可本次未解析 | 保留许可/出处/commit/本地哈希；只自主实现领域思想，指南未授权原文只留自撰摘要 | 不运行下载的 PHP/Django，不复制上游运行代码；未知许可和获取失败必须可见 |
| DB11 真诚迁移与研究更新 | OJS 有修复历史 stage/decision 迁移；当前系统只有简化初筛和合成工作台 | legacy UUID/回执保留、显式 legacy provenance；源码基线单独保存 | 不为旧稿虚构查重/审批/文件；不静默改旧研究哈希掩盖差异 |

| DB12 检查证据不改稿件 | OJS 的文件/编辑决定分离；Janeway 的 checklist 留 completed_by/completed_on | CheckRun 独立关联同刊 FileObject，人工报告复核与负责人最终确认分开；每步骤最多一个 finalized | 不为补报告改冻结 VersionFile，不把人工结论冒称自动查重；数据库确认/版本/步骤/归因一致，finalized 禁改删/TRUNCATE |

完整来源定位在 JSON 的 `decisions[].source_refs` 和 `models[].field_groups[].source_refs`，并由离线脚本逐表、逐字段比对。DB09 后续现代制作选择还应复查 Janeway [typesetting 源码证据](../janeway/sources/typesetting-model-fields.txt) 与 [旧 production 证据](../janeway/sources/production-model-fields.txt)，避免在下一切片混用。

## 首批 14 个模型的边界

这里的 14 是“既有 Manuscript 扩展 + 13 个新模型”，不是 14 张全新表。C 切片另增加 CheckRun，JSON 放在 `extension_models`，总映射15类。所有 `publishing_` 子表关联真实 Manuscript，旧 `/workbench` fixture 不升级为正式数据源。

| 项目类 | 关键来源与字段 | 本项目关键约束/区别 |
| --- | --- | --- |
| Manuscript | OJS submissions.submission_id/context_id/status；Janeway Article.journal/owner/stage | 保留 UUID，新增 workflow_kind；editor 可空；UNIQUE(id,journal_id) 支持租户外键 |
| SubmissionWorkflow | OJS current_publication_id/stage_id，Janeway current_step/date_submitted | 一稿一个当前工作流；期刊内编号唯一；当前/草稿/接受版本指针同稿；revision 乐观并发 |
| ManuscriptVersion | OJS publications.version + publication_settings；Janeway Article 元数据与冻结作者模式 | 这是稿件内容版本；(manuscript_id,version_no) 唯一；提交后 DB 冻结；结构字段不埋 JSON |
| VersionAuthor | OJS authors/email/seq、author_affiliations.ror；Janeway FrozenAuthor | 同版排序唯一；至多一个通讯作者；父版冻结后不可插改删；署名不赋权 |
| FileObject | OJS files.path/mimetype；Janeway File 文件名/owner/privacy | SHA/大小/租户/实际 UTF8 验证为自有加固；不可覆盖 blob；1MiB 小 txt/md 范围 |
| VersionFile | OJS submission_file_revisions、stage/viewable；Janeway ReviewRound.review_files | 同稿/同刊 compound FK；首片 version+purpose 单槽；冻结后引用不可改 |
| Assignment | OJS stage_assignments/recommend_only，user_user_groups 开始结束；Janeway AccountRole | 有期限本稿 capability；活动处理编辑至多一名；撤销保留历史 |
| StepRun | OJS review_rounds(stage,round,status)；Janeway ReviewRound/WorkflowLog | step+cycle 独立历史；执行结果与人类放行分开；不是空泛状态标签 |
| WorkItem | Janeway Task.assignees/due/completed；OJS review_assignments 时间事实 | 明确同稿型 FK，拒绝泛型 object_id；assignee/status/due 和 journal/status/due 索引 |
| FormDraft | OJS publication_settings；Janeway DecisionDraft/Article 字段 | 有来源、有修订候选；规范化 version/author 是真值；草稿不承载权限/状态 |
| ActionProposal | Janeway DecisionDraft，OJS edit_decisions/Repository | 完整不可变内容摘要、责任人、修订、政策、到期；旧快照失效；无 Agent 最终确认工具 |
| HumanConfirmation | OJS editor_id/decision/date_decided；Janeway checklist completed_by/completed_on | proposal 唯一确认、不可变；session_hash 为证据字符串而非可删除会话 FK |
| ActionReceipt | 上游日志是参考，不声称有同等幂等回执 | user+journal+request 唯一；input_digest 防错用；响应与动作/审计同事务 |
| PublishingChatTurn | 上游稿件身份、WorkflowLog 与 review visibility 为上下文边界参考 | 新增对话事实；按角色/对象裁剪；保留当时上下文；模型只能提议 allowlist 工具 |

字段级映射刻意区分 `adapted_pattern` 与 `project_governance`。摘要、幂等键、不可变确认、策略版本、SQL 冻结、会话证据等不是伪造的上游字段；`source_refs` 说明为什么需要它，不能当作同名上游实现。

## 持续研究门禁

在仓库根目录运行 `python scripts/check-research-library.py`。它只用标准库，不联网，不执行上游代码：

1. 读取实际 OJS、Janeway manifest；逐份检查 artifact 路径、SHA-256、HTTPS 来源/固定版本/commit、用途/日期与许可声明。OJS 未解析许可的三份指南只允许自撰摘要，并要求独立原文哈希；失败获取单列计数，不当成功来源。
2. 验证 GPL/AGPL 许可文本存在、Janeway CC BY 文档保留来源/署名/许可；这里验证声明及保留证据，不是法律许可审计。
3. 解析表/模型/CSV 索引，核对 source ID、类/表/字段引用以及 14 模型契约覆盖，避免有书目无对应实现决策。引用字段必须实际在固定索引中。
4. current-system manifest 是 `354c930...` 的**历史基线**：以本地 `git show baseline:path` 校验那份真实字节。工作树有意开发变化另列 `worktree_drift`，不把它冒称基线没变；要要求新鲜度，运行 `--strict-current`。历史内容缺失/哈希不符仍失败。升级基线应建立显式新研究批次，不改旧 SHA 让门禁变绿。
5. 任意缺文件/哈希变化/非法来源引用/缺许可/模型缺覆盖/实现字段声明漂移返回非零。输出 JSON 包含成功来源数、未知许可摘要数、失败获取数和基线漂移清单；`--library` 可指定隔离副本做负向实验。

新增切片需先查两套官方固定来源，记录“观察→采用/拒绝→新增约束→验收”，再更新映射和模型/迁移绑定。迁移绑定非空时脚本还要求仓库中实际存在对应 Alembic revision；implemented 模型必须在指定源码 AST 找到类，并逐字段核对声明、位置及完整覆盖。扩展模型还要在其引用规格中出现，不能无来源地随意加名。脚本不能替代数据库迁移/并发/权限测试或 `scripts/verify.sh`。

当前没有原生子 Agent Token/API 费用遥测，值保留 null；未执行的功能/迁移验收不能填为成功。邮件始终 `EMAIL_SEND_ENABLED=false`，正式录用、拒稿、撤稿和公开发布保留人类权限。

## 首轮研究门禁验证（历史）

2026-11-02 实际运行标准门禁返回 0、`ok=true`：OJS 39 份和 Janeway 35 份本地来源通过哈希；18 项当前系统历史基线通过本地 git 字节核验；索引包含 OJS 59 表/412 字段、Janeway 61 模型/553 字段、基线16表；设计覆盖14类/159个字段、11项采用/拒绝决策。三份 OJS 指南许可未解析但只保存自撰摘要，4项获取失败均单列。当前基线漂移4项（models/main/security/policy）是正在开发的工作树与旧研究批次的差异，未标作哈希验证成功的“当前版本”。

隔离复制研究库后完成9项实验：完整副本返回0；篡改artifact、缺artifact、未知源码许可、杜撰上游字段、CSV与JSON不一致、OJS声明索引改写、基线类行号改写、`--strict-current` 旧基线漂移，8项都按预期返回1并给出具体错误。原研究材料未改动。Ruff check 与 format --check 均通过。临时详细输出位于 `/tmp/publishing-ojs-research/comparison-gate-{positive,negative-tests}.json`，临时缓存可清理，正文是持久验证记录。这些证据只覆盖研究门禁，未运行或冒称完整应用/迁移验收。

## C 切片检查组件与实际实现绑定

`CheckRun` 的16个字段已映射并绑定真实源码 `apps/api/publishing/domain/checks.py` 和 `09b73e6a1c22`，后继 `f8a12d4c6e90`。基础14类的159字段也绑定各自实际源码、类/字段行号和声明，以及 f8a 迁移。`implemented` 仅意味着代码已存在且静态一致，不代表核心/API/页面已完成集成；主负责人维护公共隔离库升级与后续端到端验收。

C 组件导出 `CheckInput`、`CheckMaterial`、`CheckFileEvidence`、`CheckMaterialFile`、`CheckDeclarations`、`PreparedCheck` 和纯函数 `prepare_check(kind,payload,material)`。它验证预审完整性、相似度报告人工复核、匿名稿件筛选、主编范围、编辑质量这5类 pass/return 建议；不决定权限、不读写DB、不推进状态、不调用模型，也无批准/发信能力。退回必须有原因；通过有各关口明确人工声明。实际文件读取/哈希、分派/COI/修订及确认关口仍由 Action Gateway 在准备和最终确认时双重核对。

CheckRun 使用同稿版本/步骤/确认和同刊报告复合FK；报告引用独立 FileObject，绝不修改已冻结 VersionFile。finalized 检查须有已冻结版本、对应 proposal 摘要/版本/workitem步骤/责任人/准备人一致的 confirm 记录；最终行禁止改删/TRUNCATE，partial UNIQUE 保证每step最多一条最终检查。相似度 `check_method=manual_review`，明确不是自动查重。空表可降级，有任何检查证据时降级拒绝。

2026-11-02 最终组件测试实际 **48 passed，2.29秒**，1项既有 Starlette/httpx 弃用warning；使用55433隔离PostgreSQL的随机事务schema演练，既不更新公共 alembic_version，也不触碰主库。测试覆盖真实迁移/空表降级、跨稿/跨刊/错误步骤版本/查重报告/未冻结或错误确认/错误归因拒绝、两个独立 proposal+confirmation 的同step最终唯一、最终证据改删/TRUNCATE拒绝，以及 typed输入/材料/人工声明。

实现绑定后研究门禁实际返回0：上游材料74份、历史基线18项仍匹配；15类/175个字段实现逐项对应、12项采用拒绝决策通过。研究门禁与组件Ruff检查通过；完整应用回归与业务浏览器验收由主负责人继续执行。

绑定后又实际运行11项离线隔离实验：完整15类副本返回0，其余10项按预期返回1；原8项负向场景之外，新增“实现字段声明绑定篡改”和“不存在的迁移revision”均被拒绝。保留的研究源码和项目运行文件没有为这些实验临时改写。
