# Publishing OS 数据库决策：把成熟出版经验变成可验证约束

更新：2026-11-03。依据 [OJS 研究](../ojs/README.md)、[Janeway 研究](../janeway/README.md)、[现有系统基线](../current-system/README.md) 和 [spec007 数据契约](../../../../specs/007-data-contract.md)。这份文件区分设计建议、静态实现绑定与已执行组件测试，不能据此声称尚未验收的服务或UI已完成。[机器可读映射](source-to-implementation.json) 的基础及扩展模型给出具体上游表/类/字段、源码位置、本项目加固和验收目标。现覆盖25类/323字段，基础 f8a、C09b、D10c、E11d、F12e 分层绑定；下文各节记录对应组件阶段证据，整个项目当前已执行的服务/浏览器/完整验收以 [PROGRESS](../../../../PROGRESS.md) 为准。

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

| DB13 固定轮次原子封存 | OJS review_rounds/round_files；Janeway ReviewRound.review_files 与冻结题目 | Round initializing→文件→seal open→完整初始邀请同事务；显式closing_confirmation绑定finish_review | 不让initializing提交、不追加/替换已封存材料；真实双连接验证不可见/封存及parent锁等待边界 |
| DB14 邀请尝试和grant分开 | OJS assignment有请求/确认/拒绝/取消及普通reviewer-round index；Janeway对应时间/COI | attempt_no加有效占位partial UNIQUE；接受后才有reviewer typed grant；重邀新任务，不改旧attempt | 拒邀不退稿；submitted不能同轮重邀；响应硬截止、报告soft due；服务访问投影另行验收 |
| DB15 报告和最终决定分开 | Janeway逐题快照、原答/编辑版/可见性/私密评论；OJS form responses和decision分层 | Report固定本轮表单；作者/编辑私密文本分列；完整人类提交后冻结 | draft不计完成；D没有chief决定/作者release/真实发信；匿名DTO与UI服务集成仍待root |

| DB16 主编决定与minor依据链 | OJS recommend_only/decision分离，Janeway DecisionDraft及RevisionRequest | 当前版本完成编辑建议后主编独立选择；basis_round只同稿，旧轮通过正式minor提交与当前复核桥接 | 不强制主编照抄建议，不误令V3 base等于R1V1；DB查一跳，完整minor归纳由服务遍历 |
| DB17 匿名发布快照 | Janeway逐题作者可见/私密与FrozenReviewFormElement，OJS responses | 显式chief批准的精确author-only源投影；共享需本人声明已检查文本匿名 | 即使批准payload含私密字段且hash匹配仍拒绝；不自动去标识或开放原始report |
| DB18 正式修回 | Janeway RevisionRequest请求/截止/回应/完成、OJS修回决定及文件轮次 | 新Request+新draft同事务；owner确认真实response和新冻结版本后提交；major必新轮 | 不覆盖原稿/删改计划，不把上传即当完成，不用旧确认批准新内容 |

完整来源定位在 JSON 的 `decisions[].source_refs` 和 `models[].field_groups[].source_refs`，并由离线脚本逐表、逐字段比对。DB09 后续现代制作选择还应复查 Janeway [typesetting 源码证据](../janeway/sources/typesetting-model-fields.txt) 与 [旧 production 证据](../janeway/sources/production-model-fields.txt)，避免在下一切片混用。

## 首批 14 个模型的边界

这里的 14 是“既有 Manuscript 扩展 + 13 个新模型”，不是 14 张全新表。C 切片增加 CheckRun，D增加4个审稿实体，JSON 放在 `extension_models`；当前总映射22类/289字段，含E的EditorialDecision、DecisionReportRelease与RevisionRequest。原基础14类在D增补Assignment/WorkItem的3个typed字段，并给VersionFile加triple parent key。所有 `publishing_` 子表关联真实 Manuscript，旧 `/workbench` fixture 不升级为正式数据源。

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
3. 解析表/模型/CSV 索引，核对 source ID、类/表/字段引用、基础14类和spec008扩展模型/字段的契约覆盖，避免有书目无对应实现决策。引用字段必须实际在固定索引中。
4. current-system manifest 是 `354c930...` 的**历史基线**：以本地 `git show baseline:path` 校验那份真实字节。工作树有意开发变化另列 `worktree_drift`，不把它冒称基线没变；要要求新鲜度，运行 `--strict-current`。历史内容缺失/哈希不符仍失败。升级基线应建立显式新研究批次，不改旧 SHA 让门禁变绿。
5. 任意缺文件/哈希变化/非法来源引用/缺许可/模型缺覆盖/实现字段声明漂移返回非零。输出 JSON 包含成功来源数、未知许可摘要数、失败获取数和基线漂移清单；`--library` 可指定隔离副本做负向实验。

新增切片需先查两套官方固定来源，记录“观察→采用/拒绝→新增约束→验收”，再更新映射和模型/迁移绑定。迁移绑定非空时脚本还要求仓库中实际存在对应 Alembic revision；implemented 模型必须在指定源码 AST 找到类，并逐字段核对声明、位置、完整覆盖和table_args约束声明。D字段必须实际出现在10c迁移的create_table/add_column AST，57项D命名FK/CHECK/Unique/index还须同时存在模型和迁移声明中；D迁移源码哈希/后继/SQL函数及deferred trigger也固定核验。扩展模型还要在其引用规格中出现，不能无来源地随意加名。脚本不能替代数据库迁移/并发/权限测试或 `scripts/verify.sh`。

当前没有原生子 Agent Token/API 费用遥测，值保留 null；未执行的功能/迁移验收不能填为成功。邮件始终 `EMAIL_SEND_ENABLED=false`，正式录用、拒稿、撤稿和公开发布保留人类权限。

## 首轮研究门禁验证（历史）

2026-11-02 实际运行标准门禁返回 0、`ok=true`：OJS 39 份和 Janeway 35 份本地来源通过哈希；18 项当前系统历史基线通过本地 git 字节核验；索引包含 OJS 59 表/412 字段、Janeway 61 模型/553 字段、基线16表；设计覆盖14类/159个字段、11项采用/拒绝决策。三份 OJS 指南许可未解析但只保存自撰摘要，4项获取失败均单列。当前基线漂移4项（models/main/security/policy）是正在开发的工作树与旧研究批次的差异，未标作哈希验证成功的“当前版本”。

隔离复制研究库后完成9项实验：完整副本返回0；篡改artifact、缺artifact、未知源码许可、杜撰上游字段、CSV与JSON不一致、OJS声明索引改写、基线类行号改写、`--strict-current` 旧基线漂移，8项都按预期返回1并给出具体错误。原研究材料未改动。Ruff check 与 format --check 均通过。临时详细输出位于 `/tmp/publishing-ojs-research/comparison-gate-{positive,negative-tests}.json`，临时缓存可清理，正文是持久验证记录。这些证据只覆盖研究门禁，未运行或冒称完整应用/迁移验收。

## C 切片组件绑定（历史组件阶段）

`CheckRun` 的16个字段已映射并绑定真实源码 `apps/api/publishing/domain/checks.py` 和 `09b73e6a1c22`，后继 `f8a12d4c6e90`。基础14类的159字段也绑定各自实际源码、类/字段行号和声明，以及 f8a 迁移。`implemented` 仅意味着代码已存在且静态一致，不代表核心/API/页面已完成集成；主负责人维护公共隔离库升级与后续端到端验收。

C 组件导出 `CheckInput`、`CheckMaterial`、`CheckFileEvidence`、`CheckMaterialFile`、`CheckDeclarations`、`PreparedCheck` 和纯函数 `prepare_check(kind,payload,material)`。它验证预审完整性、相似度报告人工复核、匿名稿件筛选、主编范围、编辑质量这5类 pass/return 建议；不决定权限、不读写DB、不推进状态、不调用模型，也无批准/发信能力。退回必须有原因；通过有各关口明确人工声明。实际文件读取/哈希、分派/COI/修订及确认关口仍由 Action Gateway 在准备和最终确认时双重核对。

CheckRun 使用同稿版本/步骤/确认和同刊报告复合FK；报告引用独立 FileObject，绝不修改已冻结 VersionFile。finalized 检查须有已冻结版本、对应 proposal 摘要/版本/workitem步骤/责任人/准备人一致的 confirm 记录；最终行禁止改删/TRUNCATE，partial UNIQUE 保证每step最多一条最终检查。相似度 `check_method=manual_review`，明确不是自动查重。空表可降级，有任何检查证据时降级拒绝。

2026-11-02 最终组件测试实际 **48 passed，2.29秒**，1项既有 Starlette/httpx 弃用warning；使用55433隔离PostgreSQL的随机事务schema演练，既不更新公共 alembic_version，也不触碰主库。测试覆盖真实迁移/空表降级、跨稿/跨刊/错误步骤版本/查重报告/未冻结或错误确认/错误归因拒绝、两个独立 proposal+confirmation 的同step最终唯一、最终证据改删/TRUNCATE拒绝，以及 typed输入/材料/人工声明。

实现绑定后研究门禁实际返回0：上游材料74份、历史基线18项仍匹配；15类/175个字段实现逐项对应、12项采用拒绝决策通过。研究门禁与组件Ruff检查通过；完整应用回归与业务浏览器验收由主负责人继续执行。

绑定后又实际运行11项离线隔离实验：完整15类副本返回0，其余10项按预期返回1；原8项负向场景之外，新增“实现字段声明绑定篡改”和“不存在的迁移revision”均被拒绝。保留的研究源码和项目运行文件没有为这些实验临时改写。

## D 轮次/邀请/报告组件绑定（2026-11-03）

正式数据约定见[spec008](../../../../specs/008-peer-review-data-contract.md)，上游观察与取舍见[邀请/评审/修回设计研究](review-revision-design.md)。root已复制模型/迁移组件到主线；本节只记录**50项模型/迁移组件测试通过，服务/UI集成待root**。没有把新表、metadata升级或纯模型测试称作可运行的审稿业务链。E主编决定、修回与报告Release表尚未在D创建。

| 项目模型/扩展 | 精确来源模式 | 当前模型/约束选择 |
| --- | --- | --- |
| ReviewRound：21字段 | OJS review_rounds 的submission/stage/round/status；Janeway ReviewRound的article/round_number/review_files/date_started；BaseReviewFormElement/FrozenReviewFormElement | 固定冻结稿件版本、表单/材料digest、required_reports/policy；initializing只在事务中存在，deferred guard拒绝未seal或漏插初始邀请；closing_confirmation_id明确绑定finish_review与完整清单 |
| ReviewRoundFile：8字段 | OJS round_files与review_files；Janeway ReviewRound.review_files和File.privacy | 双triple FK确保同稿同版；仅真正blinded/reviewer文件；服务器匿名名；parent FOR UPDATE后只允许initializing插入，seal后不能追加/改/删/TRUNCATE |
| ReviewInvitation：25字段 | OJS review_assignments的reviewer/round/请求接受截止/拒绝取消/COI；Janeway ReviewAssignment相同生命周期事实；OJS通用invitations只作为分离参考 | attempt_no唯一加pending/accepted/submitted有效占位；拒绝/取消/过期可新attempt，submitted不可重邀/取消；绑定完整匿名消息、收件人、版本、期限与对应人类确认；不复用旧attempt |
| ReviewReport：16字段 | OJS recommendation/form responses；Janeway ReviewAssignmentAnswer、BaseReviewFormElement与FrozenReviewFormElement、private/author visibility字段 | 一邀请一报告，round/version/reviewer从不可变Invitation派生；固定题目快照；author_text/editor_private_text分列；提交完整内容与本人确认一致后禁改删；D未实现向作者分享 |
| Assignment：新增review_invitation_id | OJS stage_assignments/user_user_groups及Janeway ReviewAssignment.acceptance | reviewer capability必须关联typed invitation，接受前不能grant；nonreviewer不能带target；有效索引与普通capability分开，结束后不可重激活或另插同邀请grant绕过 |
| WorkItem：新增review_invitation_id/review_report_id | Janeway Task泛型目标警告；OJS逐reviewer assignment生命周期 | typed target互斥、同稿FK；recipient/version/独立StepRun匹配；旧全局唯一改为三个partial UNIQUE；完成必须绑定真实response/report确认，不能伪完成管理步骤 |
| VersionFile：无新字段，增加parent UNIQUE | OJS轮次固定文件/Janeway round文件集 | UNIQUE(id,manuscript_id,version_id)支撑RoundFile真正同版FK；不修改冻结VersionFile内容，也不从“当前稿件目录”动态取文件 |

字段和命名约束均在JSON指向真实 `apps/api/publishing/domain/review_models.py` / `models.py` AST行号与声明；D的70个新实体字段和3个既有关系新字段，共73个列绑定10c84f7a2d31的真实create_table/add_column，57项命名约束绑定同一迁移。基础14类原f8a与C09b绑定仍保留；约束的规范化改造另列D revision，而非把新字段误归原迁移。

D的原子顺序是：opening confirmation→Round(initializing)→固定RoundFile→seal open→全部初始邀请/响应待办；接受确认→Invitation accepted→真实reviewer grant→Report draft/报告待办；提交确认→冻结Report→Invitation submitted→完成报告待办；取消确认→Invitation cancelled→结束grant/封存withdrawn草稿/取消未完成任务；finish确认清理后才写Round.closed与closing_confirmation_id。新增事件在bump前flush检查当前revision；历史grant核验不要求它仍是最新revision。单纯达到报告数量不会自动录用、退稿或创造编辑完成事实。

全部实现/测试在隔离工作树 `/tmp/publishing-v01-review-models` 完成；真实PostgreSQL50项测试用24.70秒通过，1项既有Starlette/httpx弃用warning。包括从初始至D完整迁移链的临时schema、metadata零漂移、空表降级/有数据拒绝降级、缺材料/漏邀请deferred失败、确认/COI/角色/版本/内容/私密分区、接受硬截止/报告soft due、取消清理与终态历史。组件agent没有升级公共head；root后续执行公共隔离库升级/旧链回归及服务接线是另一组验收，不能混写为本轮成功证据。

双连接实验在仅新建随机合成schema内提交setup后执行，最终仅DROP该随机schema：初始化未提交、seal未提交、seal提交后追加均报P0001；持Round parent FOR UPDATE锁时另一连接300ms超时报55P03（本次0.3017秒），释放后仍报P0001，始终只有1份批准材料。源码与详细顺序可在tests/api/test_peer_review_models.py复现，JUnit证据在隔离树artifacts/peer-review-models.xml；未触碰public业务表或主库/密钥。

研究门禁还固定本轮已验证D迁移SHA-256与down_revision，核对9个关键SQL函数及4个deferred trigger；它是静态来源/实现一致性检查，不能替代运行数据库约束/匿名API/模型history/replay或浏览器验收。之后若修改SQL/关系，应重新测试并显式更新对应映射，不可仅改hash来让检查变绿。

本次D映射更新实际运行研究门禁返回0：OJS39/Janeway35来源与18项历史基线仍通过；19类/248字段、73个D列revision绑定、57项D命名约束、3个复合FK helper语义快照、1份spec008及已验证D迁移通过静态一致性检查，采用/拒绝决策共15项。保留原10项负向并新增9项D负向，共20项隔离实验：完整副本返回0，其余19项分别对篡改/缺失/未知许可/假源字段/CSV与索引漂移/基线或实现字段漂移/错误revision/严格基线漂移、D table_args、typed列错迁移、缺或假FK/Unique、spec覆盖/路径、迁移hash、字段组归属矛盾、FK helper语义篡改返回1。没有为实验改写任何应用或SQL文件；只改隔离研究库副本。Ruff check与format检查通过。详细临时输出为 `/tmp/publishing-ojs-research/D-research-gate-{positive,negative-tests}.json`；正文为持久记录，临时缓存不承担后续运行依赖。

## E 主编决定、匿名反馈与正式修回组件（2026-11-03）

依据[spec009](../../../../specs/009-decisions-and-revisions.md)，增加3类/41字段，绑定真实 `decision_models.py` 与 `11d95a8b3e42_editorial_decisions.py`（后继10c），在domain/__init__只做无DB IO的metadata注册。组件只在 `/tmp/publishing-v01-decision-models` 工作树开发，用55433随机事务schema演练，未升级public head。主线服务/浏览器/完整verify由root另行验收；本节的44项组件证据不能等同E/F或整个Goal完成。

| 模型 | 上游字段/关系模式 | 本项目落地边界 |
| --- | --- | --- |
| EditorialDecision：17字段 | OJS edit_decisions的submission/round/stage/editor/decision/date，recommend_only与决定校验；Janeway DecisionDraft、RevisionRequest | unique human confirmation和chief step，同稿version/basisRound/推荐/复核FK；只插入record_decision人类确认；主编可以不同于编辑建议；接受绑定实际production负责人完整快照 |
| DecisionReportRelease：8字段 | Janeway for_author_consumption、逐答案author_can_see、冻结题目与私密文本分离；OJS review_form_responses | unique(decision,report)/(decision,ordinal)，ordinal>=1；仅basisRound已交报告；精确safe{author_text,answers,questions}源投影，questions只key/label/kind/required；不可改删/截断 |
| RevisionRequest：16字段 | Janeway article/editor/type/notes/response_letter/requested/due/completed，OJS当前有效修回决定与轮次文件 | 同稿决定/base/draft/submitted/author确认FK；一稿仅一requested；请求与planned新draft同人类决定事务，major必rereview；除requested→submitted4字段外不可改，无session FK |

初始决定与所有批准release/planned请求由deferred bundle保证同事务齐全。Release不是“允许作者读原始Report”的标志，作者只能读负责人的安全反馈DTO。即使approved payload自己包含reviewer_id、editor_private_text或private answer并配套重算hash，数据库也会根据原报告与固定表单重建safe source投影而拒绝。结构隔离不宣称已自动清除自由文本里的身份，因此共享必须有 `share_reports_anonymity_reviewed=true` 的人类声明，服务还需实际审核正文。

提交修回顺序是确认完整新版本→完成当前owner任务→freeze新版本→Request submitted→更新flow.current/draft指针。DB检查本人/同稿/准确request计划/真实response VersionFile与批准文件hash，实际CAS bytes与完整声明仍由gateway重校。minor V2及再次minor V3都可使用R1(V1)，只要有本次submitted minor请求、来源决定仍指R1、当前ready_for_chief复核和当前编辑建议；不得把V3 base V2错误强制等于R1 V1。数据库只校验一跳事实，服务完整遍历链；major不能靠这个桥接绕过新轮。

本次实际 **44 passed，26.76秒**，1项既有Starlette/httpx弃用warning；保留完整初始→C→D→E迁移链与Base.metadata零漂移比较、空表downgrade/有历史拒绝downgrade、精确动作/任务/角色/版本/revision/载荷、两次minor到V3、major旧轮拒绝、真实response缺失/未冻结/非owner、计划/决定/反馈不可改删/TRUNCATE、审批集合缺失不能commit及批准payload私密注入负向。原DDL只检查linked_user的chief/production历史作者邮箱两例先实际失败；只补该决定guard两处历史邮箱冲突信号后通过。邮箱只作冲突信号，绝不凭邮箱授予访问。模型和签名未变；root对已有隔离数据只重装该函数，没有downgrade/删数据，这不代表component agent做了public迁移。

当前来源映射覆盖22类/289字段、114个D/E新增列、93项命名约束、2份已验证迁移指纹和2份增量契约。研究门禁继续核验原OJS39/Janeway35材料与18项历史基线；spec009的编号/反引号类声明现在与spec008粗体声明一样进行严格完整覆盖，不能漏掉E实体。原有负向实验仍保留，新增E契约/字段/约束/迁移指纹与deferred guard目标实验另记；没有为了通过门禁弱化任何字段、FK或hash检查。

E映射的标准研究门禁实际返回0：22类/289字段、114个D/E新增列、93项命名约束、7张新增表的完整命名约束集合、3个FK helper、2份合同/迁移指纹与18项采用拒绝决策全部对应；原74份上游材料/18项历史基线仍匹配。新增10项隔离门禁实验：完整副本返回0；E合同漏模型、E列错绑D迁移、漏命名FK、table_args漂移、E迁移hash变化、错误前序revision、缺deferred bundle、上游假字段、上游artifact hash篡改这9项均返回1。仅改隔离研究库副本，没有改模型/SQL来制造通过；Ruff与格式检查通过。当前实验明细在隔离树artifacts/E-research-gate-{positive,negative-tests}.json。

## F 校样包、作者响应与鉴权本地预览组件（2026-11-03）

正式字段和界面合同见[spec010](../../../../specs/010-production-local-preview.md)，上游观察见[制作/校样设计研究](production-preview-design.md)。本节只记录独立模型组件与研究门禁，不替代 lead 在 PROGRESS 中维护的服务、权限、浏览器及完整 verify 证据，也不宣布整个 Goal 完成。

本次再次核对固定源码：[OJS OJSMigration.php](https://github.com/pkp/ojs/blob/0f2de4ff3f399a65dbe5c24c035529c0ff9bc976/classes/migration/install/OJSMigration.php#L266) 把 publications 与 publication_galleys 分开，galley 有独立 publication/file、label、is_approved；[Janeway production/models.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/production/models.py#L14) 区分制作责任、TypesetTask 的输入材料/产出文件与 editor_reviewed；[proofing/models.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/proofing/models.py#L61) 再区分 ProofingRound、ProofingTask 和 TypesetterProofingTask 更正任务。这些是复用关系的证据，不是声称两者已有与本项目完全相同的人类内容审批机制。

上游的边界同样需要明确：固定 Janeway ProofingRound.number 在本库摘录中只有排序，没有 assignment/number UNIQUE；ProofingTask 把多人、多文件/galley、nullable proofreader 与可修改时间事实组合在任务中。OJS galley.submission_file_id 可空、可使用 remote_url，is_approved 默认0；该 install 定义并不提供本项目需要的“确切作者逐包确认+同版同包响应”复合关联。它们适合其完整应用语义，不能据此推断我们的 raw SQL 约束已足够。F 选择较窄的 txt/md 单校样包；保持不可变、递增 package_no 和逐包本人响应，不直接复制其任意远程载体、任务泛化或删除级联行为。

| 决策/模型 | 本次采用 | 明确拒绝与约束 |
| --- | --- | --- |
| DB19 / ProofPackage：13字段 | 录用版与制作材料分离；独立 FileObject；package_no；同稿录用决定；安全元数据、文件、制作人和完整人工确认固定 | 不向冻结 VersionFile 追加 proof；不从 latest timestamp 或 dedup blob.original_filename 猜本稿校样；当前 production role/grant 可依法再分派，历史作者 link/邮箱冲突均拒绝 |
| DB20 / ProofResponse：8字段 | 原投稿作者对每个确切包 approve 或 request_corrections；一包一结果；corrections 说明至少20字；确认后不可修改 | 不把更正当稿件 reject；不接受模型代勾声明；旧包/别包响应不能确认新包；完整 canonical8 包、accepted版、hash/metadata/package_digest 都须一致 |
| DB21 / PublicationPreview：13字段 | 同包作者 approve 后，当前制作人独立确认本地预览；沿用已批准 metadata/file/name；明确 local_only | 不是公开 Publication/Galley，不注册 DOI、不设置 published、不发送通知；复合 FK 同时绑定 package/manuscript/acceptedversion 及 response/manuscript/package，不能用另一包的 approve |

34个字段逐项绑定 `apps/api/publishing/domain/production_models.py` 的实际 AST 位置、类型和 mapped_column 声明，29项命名 FK/Unique/CHECK 逐项绑定模型及 `12e06b9c4f53_production_local_preview.py`（后继11d）。Package UNIQUE(id,manuscript_id,accepted_version_id) 与 Response UNIQUE(id,manuscript_id,package_id) 是 Preview 强复合 FK 的父键；独立同刊 FileObject 不授予下载权限，真实 CAS 字节、访问投影、撤权幂等重放与页面转义仍由服务验收。

公开形 metadata 从冻结录用版和有序 VersionAuthor 重建，只包含 schema_version/title/abstract/language/article_type/keywords/authors/funding_statement；authors 只包含 name/orcid/affiliations/corresponding/contributions，去除邮箱、账号关联、声明/COI。冻结 file **严格5键** id/filename/sha256/byte_size/media_type，不把下载URL或验证显示字段写入材料摘要；包 **严格8键**，F envelope.version 必须 JSON null，但 ActionProposal.version_id 仍必须是真实 accepted 版。数据库独立重建安全对象，不能靠“前端隐藏额外字段”。

事务顺序为创建确认→完成当前 typed 任务与 StepRun→插入不可变事实→创建下一任务。send_proof 的完成 step 同次写新 package_id 和 previous_package_id；payload 明确绑定同一个 previous_package_id。第二包开始必须来自紧邻前包的真实 request_corrections，hash 只与此前包比较，不能将所有旧 hash 永久列黑名单：组件实际验证 A→B→A 三包可合法恢复更早内容，同时相同上一包字节、缺前包、wrong previous 或已 approve 前包均被拒绝。下一 author_proof/preview_confirmation 的 active 包由 StepRun 指针固定，不是最新上传材料。

组件已实际 **53 passed，37.10秒**，1项既有 Starlette/httpx 弃用 warning；JUnit 观察文件 `/tmp/production-models-final.xml` 的 SHA 和测试源码 SHA 已记录在映射。测试使用55433隔离库的随机事务 schema 并回滚，完整初始→C→D→E→F迁移链与 Base.metadata 比较为零差异。覆盖准确快照/私密字段注入、同刊实际校验类型、当前制作人再分派、历史作者邮箱冲突、逐包本人确认、更正链、非approve预览拒绝、过期 revision/policy/step/version、全部3表 UPDATE/DELETE/TRUNCATE 及有历史降级拒绝。它没有运行真实模型、外部邮件或公开发布，没有修改公共 head 或主库。

独立 raw SQL 实验新增两项负向，最初确实发现 payload.stage 可伪 chief_decision、WorkItem.kind 可伪 author_proof 而 StepRun/flow 仍 production 时没有被 F guard 拦住。服务另有校验，这不是未经验证的应用漏洞声明。补 `publishing_production_confirmation` 对 payload.stage/WorkItem.kind 的严格同阶段绑定后，全部53项通过；模型签名/DDL不变。root 对已有隔离数据只替换这个精确函数，无需降级/删除数据。映射同时固定完整12e迁移 SHA、9个函数名称、6个不可变/截断 trigger 和该函数标准化 CREATE OR REPLACE 指纹（472eee871a7ab2b629202ab4071c22d4fbb7e61aff1a7c79d7430a8cb55df9af）。不能只改指纹来掩盖未经测试的 SQL 改动。

研究门禁新增所有 implemented 模型的 `__tablename__` AST 精确核验、F row/truncate trigger 的事件/表/函数绑定、关键函数指纹，以及组件测试源码 hash/测试函数集合与观察证据声明核验。报告可能位于临时文件，所以离线门禁不依赖 JUnit 仍在本地、不联网或重新运行数据库；输出用 `observed_component_cases_declared_only` 标明53是已记录观察，不能把标准门禁说成再次执行了53项测试。既有上游哈希/许可、历史基线、逐字段、全量命名约束、deferred guard 和原负向实验均保留。

本次 F 研究门禁标准运行实际返回0：25类/323字段、148个D/E/F增量列、122项命名约束、10张新表完整命名约束集、24个实际domain Base类全覆盖、3份增量合同/迁移与24条D/E/F row/truncate trigger 精确绑定；OJS39/Janeway35份材料与18项历史基线仍匹配，采用/拒绝决策共21项。门禁没有重新执行53项数据库测试，只校验已记录的组件测试来源与观察声明。

另在隔离复制库完成 **20项门禁实验：1项完整副本成功、19项负向均按预期返回1**。负向包括F契约漏实体/整份合同移除/整个F切片映射移除、列误归E、源码字段声明漂移、漏命名FK、错物理表名、迁移hash/前序错绑、缺row trigger/错function、truncate错表、关键函数指纹变化、组件suite源码hash/测试函数集合/无效观察数、杜撰上游字段、严格旧基线漂移、上游artifact篡改。实验仅改临时研究库副本，未修改实现、迁移SQL、组件测试或真实来源；首次实验的严格基线断言用了错误预期文案（实际已正确返回1），纠正后完整重跑20项通过。详情为 `/tmp/F-research-gate-{positive,negative-tests}.json`，临时证据可清理，以上正文与映射保留实际结果。Ruff check、format检查及git diff检查通过；组件 Token/API费用遥测为 null。
