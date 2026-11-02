# Janeway 数据库与工作流研究

研究日期：2026-11-02。用于 Publishing OS v0.1 的架构/字段决策，不是 Janeway 集成或运行验收。本目录只读取公开资料和源码，未安装 Janeway、执行其 Python/Django 代码、运行迁移或连接出版业务数据库。

研究基线是官方仓库 [openlibhums/janeway](https://github.com/openlibhums/janeway) 的 **v1.8.4 Pegasus**，完整提交 `e24b23bd112ff7ca08097620d8a31041a25f9d26`，2026-10-27 发布。旧 BirkbeckCTP 链接仍能定位项目，但新来源统一使用 canonical 仓库。v1.9-RC-1 为预发布，不混入稳定版字段结论。v1.8.4 是编辑工作流/下载访问检查安全修订，说明角色标签本身不能替代对象与文件层授权。

先读本文件，再查 [字段字典](model-fields.json)、[逐字段平面索引](field-index.csv)、[来源清单与哈希](manifest.json)、[许可和提取方式](PROVENANCE.md)。字段字典是对固定源码 AST 的静态提取，不是执行 Django 后导出的数据库 DDL；继承字段、默认主键/FK索引、运行时翻译字段等必须另外考察。

## 可直接影响我们的结论

1. **文章身份、作者记录、账号与权限是四件事。** Article 是跨流程的稳定对象；FrozenAuthor 是独立可排序作者记录，账号关联可空。AccountRole 以期刊+账号+角色唯一，因此同期刊多角色是正常情况。不能把一个 author_id 或一个 membership.role 当作完整出版模型。
2. **阶段和子任务不能合并。** ReviewRound 固定本轮文件；ReviewAssignment 分别保留请求/接受/拒绝/完成时间。CopyeditAssignment、AuthorReview、TypesettingRound、GalleyProofing 各有生命周期。主阶段只用于整体进度，不能代替逐人工作项与轮次事实。
3. **内容版本与表单版本应冻结。** Janeway 用 FrozenReviewFormElement 保留填写时题目，编辑后的评审答案与原答案分开。我们的稿件 metadata、作者顺序/机构、审稿文件、报告题目、确认内容都应按版本/快照保存，不能只存最后一个可变 JSON。
4. **作者可见、编辑私密、公开评审是不同权限。** 一份评审的整体分享开关、逐答案可见性、原始/编辑后答案、附件可见性、作者身份匿名、公开授权均有独立字段。AI 上下文必须经过同一服务端序列化过滤。
5. **不要照搬历史设计弱点。** File.article_id 是普通整数而非外键；Article.stage 的帮助文字明确警告手改会绕过流程；Task 使用 GenericForeignKey 并有错对象类型可能误完成任务的源码警告。Publishing OS 应用真实外键、固定实体类型、确定性转换与不可变确认提升这些边界。
6. **传统系统自动通知不能直接迁入。** Janeway 指南中的接收、拒绝、新轮次、copyedit 完成可随后通知；我们的决定、稿件状态、邀请记录和邮件批准/发送必须分离，EMAIL_SEND_ENABLED=false 不改变。

## 固定源码中实际有哪些数据

下表是对模型声明的观察；右列是我们自己的设计建议，不代表 Janeway 原本具有同样的不变量。每个模型与原始行号可在 `model-fields.json` 查证。

| 业务概念 | v1.8.4 实际字段/关系 | Publishing OS v0.1 取舍 |
| --- | --- | --- |
| 稳定投稿 | submission.Article：journal、owner、title(999)、abstract、language、section、license、stage、date_started/submitted/accepted/declined/published/updated、current_step | 沿用现有 manuscript.id；把查询用状态/当前版本作为投影，保留独立流程实例和事件；未分派编辑应可空 |
| 完整元数据 | Article：non_specialist_summary、jats_article_type_override、rights、article_number、页码/总页数、is_import、publisher_name/publication_title/ISSN_override、article_agreement | 首版标题/摘要/语言/类型/关键词/作者/声明/稿件文件必须可恢复；历史导入字段不与新稿默认值混淆 |
| 关键词 | Keyword.word 全局唯一；KeywordArticle 关联文章，唯一(keyword, article)，有排序 | 学科/关键词不作为流程状态；保留来源与期刊词表，稳定步骤另列 |
| 作者与机构 | FrozenAuthor.article、author(可空账号)、名字各部分、order、is_corporate、frozen_email、frozen_orcid、display_email；ControlledAffiliation 可关联账号或冻结作者 | 作者快照挂到每个不可变稿件版本；访问授权单独赋予，不能按姓名/邮箱猜授权；顺序唯一(version, ordinal) |
| 通讯作者 | Article.correspondence_author 指账号；冻结作者可没有账号 | 通讯标记应在作者快照上，代理提交人与通讯作者不必同一人；登录账号权限另存 |
| 作者贡献 | CreditRecord 关联 frozen_author 或 preprint_author，有互斥字段检查；唯一(frozen_author, role) | 首版保留可选 CRediT 字段；勿让模型捏造贡献声明，确认后进入版本快照 |
| 资助 | ArticleFunding.article、name、fundref_id、funding_id、funding_statement | 可选资助行，区分资助机构标识与项目编号，不强迫无资助作者填写假值 |
| 投稿声明 | Article.competing_interests_bool/text、publication_fees、submission_requirements、copyright_notice、article_agreement | 保留“未回答/有/无”与完整期刊政策快照；AI不能把 false 默认值当作作者已声明无冲突 |
| 文件 | core.File：mime_type、original_filename、uuid_filename、label、description、sequence、owner、privacy、date_uploaded、is_galley、is_remote/remote_url、history、text；article_id 为普通整数 | 内容对象存 SHA256/字节数/类型/存储键/隔离检查；版本文件关系保存用途和可见性，复合外键防跨稿件，禁止直接远程URL下载 |
| 文件历史 | FileHistory 复制文件元数据和 history_seq；Article 有 manuscript/data_figure/supplementary/source 多种文件集合 | 新稿/补交/修回建立新版本与内容寻址文件引用，不覆盖旧对象；上传不等于已通过人工审核或扫描 |
| 编辑分派 | EditorAssignment.article/editor/editor_type/assigned/notified，唯一(article,editor) | 分派记录带开始/结束/职责/阶段范围与分派者；允许重分派历史，同一有效分派仅一条；通知独立 |
| 审稿轮次 | ReviewRound.article/round_number/review_files/date_started，唯一(article,round_number) | 固定 round.version_id 与评审文件摘要；轮次目标数和匿名策略快照，之后不能偷偷替换文件 |
| 邀请与评审 | ReviewAssignment.article/reviewer/editor/review_round、decision、COI、visibility、form、access_code、date_requested/due/accepted/declined/complete/reminded、is_complete | 首版可分为邀请、接受后的任务、已提交报告；这些事实不靠一个字符串或单布尔推断，不给模型邀请发送能力 |
| 私密与分享 | ReviewAssignment.comments_for_editor、for_author_consumption(false)、display_review_file、permission_to_make_public(false)、display_public(false) | 作者只见负责人正式分享的作者版报告；审稿人只见自己的报告和获准文件；公开授权另行确认 |
| 评审表单与答案 | ReviewForm 可软删；ReviewAssignmentAnswer 有原答案、edited_answer、original_element(SET_NULL)、author_can_see；FrozenReviewFormElement 一对一答案，冻结题目定义 | 后端版本化 schema + 原始报告快照 + 编辑发布版本；修改表单/编辑文字不回写评审原稿 |
| 评审附件 | ReviewAssignmentAnswerFile.answer/file/edited，唯一(answer,edited) | 附件与原/编辑版本绑定；下载也做轮次/报告授权，不只隐藏链接 |
| 修回 | RevisionRequest.article/editor、editor_note、author_note、response_letter、type、date_requested/due/completed、actions；RevisionAction 含时间和用户 | 保存逐轮修回请求、作者给编辑/审稿人的回复和新稿件版本；旧报告仍绑定旧输入 |
| 决定草稿 | DecisionDraft.article、editor、section_editor、decision、message_to_editor、email_message、drafted、editor_decision、revision_due、decline_rationale | 推荐/草稿/正式决定/通知分开；负责人确认绑定不可变完整内容、目标版本与revision，Agent无最终确认工具 |
| 文字编辑 | CopyeditAssignment：copyeditor/editor、输入/输出文件、notes、due、accepted/completed/reopened时间；AuthorReview：author/assignment/decision/date/files_updated | 可以多次文字编辑/作者复核；每次输入输出均可追溯，重新打开不抹掉前次完成记录 |
| 排版与校样 | TypesettingRound 唯一(article,round_number)；TypesettingAssignment 一对一 round，输入文件/生成 galleys；GalleyProofing 有proofreader、due、accepted/completed、proofed_files、notes、annotated_files | 首版一个制作负责人 + 作者校样确认即可，但仍存轮次、文件与明确责任，不用“制作已完成”假状态代替 |
| 发布载体 | Galley.article/file/css/images/xsl/public、type、label、sequence、remote标记；Article.render_galley 指默认呈现 | 首版只做本地可预览的安全文本/HTML/PDF文件引用，发布预览需负责人确认；不运行上游XSL或任意HTML脚本 |
| 期次 | Issue.journal、volume、issue、issue_title、date、order、issue_type、articles、editors、code、doi、isbn；Article.primary_issue 与 projected_issue 分开 | 预计归属与正式归属分开；跨刊挂载由复合外键拒绝；v0.1可只配一个本地测试期次 |
| 标识符 | Identifier.id_type/identifier/enabled/article；register() 可触发 DOI 注册逻辑 | 首版只保存内部标识与可选外部ID映射，不调用 DOI 注册；注册状态不能等同于标识字符串已存在 |
| 发布检查 | FixedPubCheckItems 一对一文章，多个检查布尔；PrePublicationChecklistItem 存article/completed/by/on/title/text | 以负责人确认、输入版本与证据摘要记录真实检查；“未配置查重”必须显示未检测，不造查重通过证据 |
| 工作清单 | Task：content_type/object_id 泛型目标、assignees多对多、completed_by、created/due/completed、完成事件；WorkflowLog含article/element/user/timestamp | 显式 manuscript/step/assignment FK、可重复工作项实例、UTC期限、索引与版本化排序；任务状态不等于业务阶段 |

## 流程与权限的实质

官方编辑指南给出 Submission → Review → Copyediting → Typesetting → Pre-publication → Published；并非每篇稿件必须经过同一路径，编辑可跳过外审、退回、开新审稿轮或采用决定草稿审批。我们不应该把这些跳转当作任何 Agent 可以调用的通用“set_stage”。自定义期刊流程应由固定且版本化的后端策略描述，例外需有权人给理由。

Janeway 的 v1.8+ 类型排版阶段整合 typesetting/proofing，新官网明确建议移除旧 Production/Proofing 工作流元素。源码仍保留 `production/models.py`、`proofing/models.py` 供兼容；它们是历史证据，不应与 `typesetting.TypesettingRound/GalleyProofing` 同时搬来构成两套新流程。

一个人可能同时为某刊编辑和作者。`editor_is_not_author`/`EditorOverride` 说明这不是单个角色名字能解决的问题。Publishing OS 首版应默认禁止作者审批自己稿件，记录回避和重新分派；不复制管理员可随意覆盖的路径。`user_can_edit_article` 从 request.journal 查具体文章，审稿权限以 assignment_id+reviewer/当前阶段检查。文件下载还有单独 `can_view_file` 检查，因此“页面不可见但下载URL能读”必须作为安全回归。

匿名化不是一个前端 badge。`can_see_pii` 对特定阶段的 section editor 也会隐藏作者身份；review visibility、作者版报告、审稿人互看、公开 consent 互不等价。新后端应先生成当前角色可见投影，再把该投影交给模型；不能让同一段完整论文/作者列表在模型上下文里泄漏。

## 历史演进给迁移的启示

- `submission/0057_frozen_email_and_orcid` 给冻结作者加无需账号即可保存的邮箱/ORCID。当前模型将冻结作者作为主作者记录，旧 Article.authors 被弃用；`0088_auto_20250506_1214` 为未提交稿回填 FrozenAuthor。说明作者快照和账号关联必须能独立迁移，不能要求所有共同作者先注册。
- `submission/0079_frozen_author_null_to_string`、`0084_remove_frozenauthor_country_and_more`、`0085_creditrecord_and_more` 体现文本空值和机构/贡献规范化持续演进。我们的nullable/空串策略要统一，字段默认值不能伪造同意，先expand/backfill再切换。
- `review/0011_keep_answers_on_form_delete` 引入冻结表单题目，原表单/题目删除后可置空，但回答仍有历史题目。这是版本化表单与不可变报告的重要先例。
- `review/0025_reviewassignmentanswerfile` 在2025年增加原/编辑两份评审附件槽，唯一(answer,edited)。一开始只留“一个附件路径”会在编辑发布视角出现返工。
- `journal/0059_alter_prepublicationchecklistitem_completed_by` 用SET_NULL保留人员移除后的检查事实。我们保留actor ID/姓名快照，审计不能因账户删除级联丢失。
- 有些历史迁移包含当前模型/测试模块导入，甚至有函数引用而未调用等可疑样式。本研究没有执行迁移，不能判断生产存量修复结果；新迁移只通过历史schema对象、显式数据范围与回滚演练，不照抄代码。

## 对现有 Publishing OS 的差距

基线为本地 `apps/api/publishing/models.py`、spec003。当前已完成的真实 DeepSeek/工作台实验不改变此表的缺口判断。

| 当前真实实现 | Janeway 提示的必需事实 | v0.1 优先交付 |
| --- | --- | --- |
| Manuscript 只有title/status和必填单editor_id | 投稿可先无编辑；作者、多文件、轮次和出版元数据独立 | 扩展稳定稿件，新增版本/作者快照/文件引用/当前步骤；保留legacy provenance |
| author_id 一个用户 | 未注册作者、排序/机构/贡献、通讯作者不同于提交人 | version_author_snapshot + manuscript_access grant；只有明确授权账号有读取权 |
| Membership 一人一期刊一个role | AccountRole 唯一(journal,user,role) | 多角色关联与职责分派分开；兼作者编辑需要冲突检查 |
| EditorialTask 唯一(manuscript,kind)、无轮次期限 | 多次审稿/修回/文字编辑/排版都能产生重复任务 | unique(step_run,kind,assignee)或相应活动任务唯一；历史不能覆盖 |
| 交互状态主要是演示JSONB | 评审轮次、邀请、报告、原/编辑内容、可见性需要关系引用 | 正式工作流新建规范化实体，JSONB限表单/快照；不扩大演示JSON做正式数据仓库 |
| 原稿为固定合成文本 | 本轮review_files、文件历史、galleys与proofed_files | 实际内容对象和版本文件，授权下载、大小/类型限制、不可变摘要 |
| 没有真实作者完整投稿确认 | 作者最后核对metadata/files/authors，完成后编辑接手 | 信息收集→缺项补全→独立审核页→作者确认→新待办，AI不代勾声明 |
| 当前Agent无最终决定工具 | 决定草稿、批准者与作者通知分离 | action_proposal+human_confirmation；绑定输入版本、完整内容摘要和expected_revision |

## 建议的 v0.1 最小关系闭环（我们的建议）

不必把61个已索引模型一次搬入。先交付支持一篇合成稿件完整走通的核心关系：

1. Journal/User/JournalRole；Manuscript保留稳定ID与当前version/phase/revision。
2. ManuscriptVersion + ordered AuthorSnapshot + VersionFile/FileObject；冻结后只能新建版本。
3. ManuscriptAssignment、StepRun、WorkItem；分派与任务分开，所有步骤有明确负责人、期限和输入版本。
4. CheckRun（检查类型、输入digest、来源、结果与人工复核），ActionProposal/HumanConfirmation（不可变内容、确认人、版本、policy及revision）。
5. ReviewRound、ReviewInvitation、ReviewReport；首版一名测试审稿人即可验证邀请响应、冲突声明、原/作者版内容与多轮修回，目标数固定于策略快照。
6. EditorialDecision/RevisionRequest；负责人决定与通知分开，作者修回产生新版本并保留原轮次。
7. ProductionWork/ProofConfirmation/GalleyPreview；首版制作、作者校样与本地预览落到真实文件、版本和人工确认，不做公开生产发布。

重要约束：同刊编号唯一；同稿版本/审稿轮次唯一；版本/轮次/确认必须属于目标稿件；作者序号唯一；同角色关联唯一；当前有效分派竞争要原子；提交文件和确认内容变更使原proposal过期；锁顺序固定；UTC due_at；任务查询先授权再计数；常查索引覆盖journal+phase、assignee+status+due、manuscript+version/round。JSONB不得成为状态机或权限唯一载体。

## 对应验收应包括

- 共同作者没有账号也可正确保存；作者更新个人资料不改旧版本署名；无明确账号grant者不能读取稿件。
- 原稿/匿名稿/补充文件有不同用途，跨稿件挂文件被DB/后端拒绝；审稿人直接猜下载URL也不能获取作者私密文件。
- 邀请未响应、已拒绝、已接受、已提交报告不可互相混淆；审稿人数不足与已有评审可并行显示。
- 改评审表后，已交报告仍展示原题目；作者默认看不到审稿人私密意见或未分享答案；公开评审需额外consent。
- 作者兼编辑不能审批自己稿件；重分派后旧负责人确认失败；模型仅收到当前角色允许的投影。
- 修回/校样新文件使旧确认失效；原轮次和作者版报告保留；重复确认UUID不重复推进。
- 制作和本地预览是事实操作，正式邮件和外部出版仍禁用。未配置真实检测服务时状态为未检测/需复核，不宣称已查重。

这些是实施建议和未来验收，不声称本研究已经创建这些表、修改模型、通过业务测试或运行 Janeway。
