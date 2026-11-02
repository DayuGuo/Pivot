# D/E 切片：邀请、审稿轮次、报告、决定与修回的数据设计

研究日期：2026-11-02。**本文是独立设计建议，不是已实现模型、迁移或权限验证的声明。**本次只写本文；未改应用代码、数据库、配置或密钥，未执行上游代码。依据既有固定 OJS 3.5.0-6 / PKP 依赖和 Janeway v1.8.4 的源码，沿用本项目更严格的人类确认与邮件禁发要求。

结论是保持四个不同事实：**邀请是否接受、报告是否提交、编辑建议是什么、主编最终决定是什么**。`declined` 只能表示本次邀请被拒绝；`recommend_reject` 是审稿/编辑建议；只有负责人确认的 `reject` 决定才能使稿件退稿。版本号、审稿轮号、邀请 attempt、修回请求号、步骤 cycle 也必须分别计数。

## 1. 固定来源与观察

OJS：`pkp/ojs 0f2de4ff3f399a65dbe5c24c035529c0ff9bc976`，实际 `lib/pkp` gitlink 为 `c4c0aa8c5293254ad253544aea230b1b607d5249`。Janeway：`openlibhums/janeway e24b23bd112ff7ca08097620d8a31041a25f9d26`。本地研究索引是静态提取，不是执行迁移后的完整数据库 DDL；“安装迁移未声明某约束”不等于已经穷尽全部运行时校验。

| 观察 | 具体证据 | 对我们的影响 |
| --- | --- | --- |
| OJS 轮次和 assignment 是两个实体 | PKP [ReviewsMigration.php:28–40](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/ReviewsMigration.php#L28)：`submission_id/stage_id/round/review_revision/status`，唯一 `(submission_id,stage_id,round)`；[48–101](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/ReviewsMigration.php#L48) assignment 保存 reviewer、轮次、推荐、COI、请求/确认/完成/截止等时间 | 不把一稿一个 status 当成所有审稿人的状态；我们的轮次版本非空、阶段非空，避开 nullable UNIQUE 在 PostgreSQL 中允许重复 NULL 的语义 |
| 拒绝邀请不等于建议拒稿 | PKP [ReviewAssignment.php:23–27、46–55](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/submission/reviewAssignment/ReviewAssignment.php#L23) 分别定义 recommendation DECLINE 与 assignment DECLINED/CANCELLED/ACCEPTED 等状态；Janeway [models.py:35–71](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L35) 分别定义 reviewer/编辑决定选项，[255–266](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L255) 有独立 accepted/declined/complete 时间 | API、DB CHECK、工具名和界面文案都必须区分 decline_invitation / recommend_reject / chief_reject |
| 历史不能用永久 round+reviewer 唯一抹掉 | PKP [ReviewsMigration.php:95–101](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/ReviewsMigration.php#L95) 注释说明账号合并后保留两份 assignment；这里是普通 index，没有永久 unique；Janeway [ReviewAssignment:197–290](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L197) 也没有声明该组合唯一 | 我们用 attempt_no + 有效 attempt partial UNIQUE；取消/拒绝后可新 attempt，原记录保留；v0.1 不做账号合并，不照搬上游放宽全部有效重复的结果 |
| 轮次文件和每人可用文件有独立关系 | PKP [ReviewsMigration.php:125–159](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/ReviewsMigration.php#L125) 有 round_files、review_files 和组合唯一；Janeway [ReviewRound:106–116](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L106) 有 `review_files` M2M，[views.py:2599–2615](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L2599) 只从该 assignment 的 round 文件取值并 hide_name | 固定轮次版本和文件集；后续稿件“当前版本”变动不能让旧轮审稿人自动读到新文件；v0.1 全轮统一盲稿，无需预造每人不同文件授权表 |
| 接受前文件访问必须是我们的新增硬边界 | Janeway [decorators.py:557–623](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/security/decorators.py#L557) 验证 assignment/账号/阶段或 access_code，但没有要求 `date_accepted`；[views.py:1068–1071](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L1068) 完成报告时甚至可补写接受时间 | 不声称上游已经保证“先接受才看稿”。本项目必须显式接受、无冲突声明、实际 reviewer Assignment 后才开放材料/报告编辑；pending 只看匿名邀请摘要 |
| reviewer 角色本身不代表无 COI | Janeway [decorators.py:379–396](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/security/decorators.py#L379) 明确说明 reviewer 装饰器不做 COI；[85–119](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/security/decorators.py#L85) 的 author/editor 防冲突还允许 override | 我们不引入自审 override；检查 owner、可验证的共同作者账号关联和用户声明，角色/机构/邮箱的猜测不能当作身份核实或授权 |
| 已提交不等于作者可见，更不等于公开评审 | Janeway [models.py:262–284](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L262)：`for_author_consumption`、`comments_for_editor`、文件显示、公开授权/公开显示分开；[views.py:2010–2045](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L2010) 作者查询只取完成且已分享报告；[3144–3149](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L3144) 分享是额外操作 | 我们初期不做公开评审；作者只读取主编确认时生成的匿名发布快照，绝不因为 report.submitted 或 reviewer 同意就直接开放原始报告 |
| 表单题目和答案均需保留当时语义 | Janeway [models.py:470–486、506–520](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L470) 保存题目类型/选项/必填/顺序/默认可见性并复制快照；[523–535、639–653](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L523) 区分原答、编辑版、逐答案作者可见及冻结题目；[0011迁移:9–33、57起](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/migrations/0011_keep_answers_on_form_delete.py#L9) 将旧题目链接改 SET_NULL 并补快照 | v0.1 使用小型固定 typed form_snapshot，而不是可变模板 FK 作为唯一语义；轮次打开时冻结，草稿/终稿都按同一份校验，不能中途换题影响历史 |
| 索引名字不能当约束 | PKP [ReviewsMigration.php:105–120](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/ReviewsMigration.php#L105) `review_form_responses_unique` 是普通 index；表单元素 FK 删除为 cascade | 我们要真实 UNIQUE、RESTRICT 和冻结快照；上游名字/应用校验不替代 DB 不变量 |
| 推荐权与决定权不同 | PKP [RolesAndUserGroupsMigration.php:108–109](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/RolesAndUserGroupsMigration.php#L108) 有 recommend_only；[decision/Repository.php:140–189](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/decision/Repository.php#L140) 核对当前阶段、deciding editor、轮次归稿；Janeway [DecisionDraft:785–837](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L785) 独立草稿/处理结果 | 编辑推荐完成后只生成主编待办；只有主编独立确认创建 EditorialDecision。不能把 reviewer/编辑意见直接写进 accepted/rejected |
| 修回请求有自己的生命周期 | Janeway [RevisionRequest:712–759](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py#L712) 存 editor/author_note/response_letter/type/requested/due/completed；[views.py:2279–2294、2332–2347](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L2279) 作者受稿件/期刊/未完成/阶段过滤，提交是单独确认 | 新版本上传不等于修回完成；必须作者确认冻结新版本，编辑再核验。minor不必新轮，major重审才创建新轮 |
| 不照搬“补齐/撤回”伪完成和删除 | Janeway [views.py:513–540](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L513) 新轮时会给未完成 assignment 写完成时间并标 withdrawn；[2214–2256](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py#L2214) 支持删修回请求/手工标完成；PKP [decision/Repository.php:304–372](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/decision/Repository.php#L304) 查询当前有效修回决定及之后文件更新 | 我们明确 cancelled/superseded，而不伪造 report submitted_at；不以文件更新时间代替作者对确切新版本的确认；保留请求/轮次原始历史 |

PKP 的通用 `invitations`（[InvitationsMigration.php:28–72](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/migration/install/InvitationsMigration.php#L28)）有 type/key_hash/user/inviter/expiry/payload/status/context，但它还用于其他职位/操作，不能直接等同审稿 assignment。我们使用专门 ReviewInvitation 的强类型关系，首版只有已登录的合成账号与站内邀请，不做 bearer access_code 或真实邮件。

## 2. 建议的最小增量实体

以下是供 root 取舍并补入正式契约的**一个主方案**。所有有 `id/manuscript_id` 的新增表均需显式 `UNIQUE(id,manuscript_id)`，供同稿外键引用；不要只照抄字段列表而漏建 parent key。沿用 String36 UUID、UTC DateTime、既有 Base、强 FK、ActionProposal/HumanConfirmation/ActionReceipt/Audit 和受控存储；不复制上游代码。首版不预造 ORCID 搜索、外部候选、复杂评分、公开评审或每人不同文件集。

### ReviewRound：一次固定版本上的正式同行评审

- 字段：`id, manuscript_id, journal_id, version_id, round_no>=1, status(open|closed|cancelled), required_reports(1..3), policy_version, review_method='double_anonymous', form_key, form_version, form_snapshot(JSONB), form_digest(SHA256), material_digest(SHA256), opened_by, opening_confirmation_id, opened_at, closed_at?, closure_reason?`。
- `version_id` 必须是本稿已冻结版本。`UNIQUE(manuscript_id,round_no)`；`UNIQUE(id,manuscript_id)`；`UNIQUE(id,manuscript_id,version_id)`；最多一个 open 轮次用 `UNIQUE(manuscript_id) WHERE status='open'`。期刊/稿件用既有 `(manuscript_id,journal_id)` FK。
- `required_reports`、版本、题目快照、材料摘要及评审方式在打开后不可变。开放后只允许一次明确的关闭/取消转移，不能把旧轮重新指向最新版本；已关闭轮不可改删。报告目标变化需独立负责人的新策略/新轮操作，不能静默把2改1以满足放行。
- 创建轮次与第一封**站内**邀请可共用一次人类确认事务。`status=open` 是允许邀请/回应的轮次状态，不代表任何 reviewer 已接受，也不代表已收到报告。稿件主阶段与等待原因单独投影；不要根据某次拒绝邀请把稿件退稿。

来源：OJS review_rounds、round_files；Janeway ReviewRound。上游 Janeway 的 M2M 文件集允许增删，我们在第一次邀请确认后冻结，属于更严格选择。

### ReviewRoundFile：轮次实际可读文件集

- 字段：`id, manuscript_id, round_id, version_id, version_file_id, role(blinded_manuscript|response), display_name, created_at`。首版至少一份 `blinded_manuscript`；re-review 可显式选择匿名化 response。
- `UNIQUE(round_id,version_file_id)`、`UNIQUE(id,manuscript_id)`。FK `(round_id,manuscript_id,version_id)` → Round `(id,manuscript_id,version_id)`；FK `(version_file_id,manuscript_id,version_id)` → VersionFile `(id,manuscript_id,version_id)`。后一个要求给既有 VersionFile 增加该 parent UNIQUE，不能只用两个独立 ID 外键假装同版本一致。
- 打开轮次时验证 purpose/visibility，清单与文件真实 SHA 都进入 material_digest；插入/更新/删除均须与轮次打开冻结串行（锁同一 parent）。不允许打开后补文件或用当前稿件目录动态代替清单。
- 给审稿人下载时由后端重验 grant，返回固定安全文件名如 `manuscript-v2.txt`，不能把 author 原文件名、uploader 或 CAS路径带入 DTO；下载端点也不能绕过匿名仓库直接访问 FileObject。

### ReviewInvitation：独立的邀请尝试和回应事实

- 字段：`id, manuscript_id, journal_id, round_id, version_id, reviewer_id, attempt_no>=1, status(pending|accepted|declined|cancelled|expired), prepared_by, invited_by, invitation_confirmation_id, message_snapshot, created_at, response_due_at, report_due_at, accepted_at?, declined_at?, cancelled_at?, expired_at?, response_reason?, conflict_status(unanswered|none|declared), conflict_text, response_confirmation_id?`。
- `reviewer_id` 首版非空，只能是本刊现有合成 reviewer；不在此表塞任意 email/外部候选。FK `(round_id,manuscript_id,version_id)` → Round triple；本稿/本刊 compound FK；确认引用同稿 HumanConfirmation。
- `UNIQUE(round_id,reviewer_id,attempt_no)`；**有效占位** partial UNIQUE `(round_id,reviewer_id) WHERE status IN ('pending','accepted')`。被拒、取消、过期可创建 attempt+1；旧行和旧响应不可重写。已提交报告的邀请保留 accepted，继续占位，首版不允许同轮同人再交第二份终稿；需要重新评审时新开轮次。这样不需要增加与报告重复的 invitation.completed 状态。
- 身份、轮次/版本、邀请内容、期限、准备/邀请人、初始审批快照不可变；只允许 pending→accepted/declined/cancelled/expired，或 accepted→cancelled（仅未提交报告时）。accepted 后的取消保留 accepted_at，另记 cancelled_at，真实表示“曾接受后撤销”，不能抹去响应历史。declined/expired/cancelled 终态不可原地重启。
- 允许接受的条件：当前登录本人、期刊匹配、pending、未过期限、轮次 open、`conflict_status='none'`、不为作者/已知关联共同作者、独立人类响应确认。接受时间不是由完成报告时补造。声明有冲突时不能创建 reviewer grant 或下载文件，可选择拒绝并把原因留给负责编辑。
- 邀请通过确认后产生站内待办，不能调用邮件发送。Agent 只能准备邀请建议/草稿。响应、报告是两种不同待办，不能用“邀请已接受”完成审稿任务。
- 建议索引 `(reviewer_id,status,response_due_at)`、`(round_id,status)`；attempt_no 在锁 round 后分配，唯一约束兜底，并发同人邀请返回可恢复409。

### ReviewReport：接受后才能编辑的真实报告

- 最小字段：`id, manuscript_id, invitation_id, status(draft|submitted|withdrawn), revision>=0, recommendation(recommend_accept|recommend_minor_revision|recommend_major_revision|recommend_reject|no_recommendation), author_text, editor_private_text, answers_json, form_snapshot, form_digest, prepared_at, updated_at, submission_confirmation_id?, submitted_at?, content_digest?`。
- `UNIQUE(invitation_id)`、`UNIQUE(id,manuscript_id)`；FK `(invitation_id,manuscript_id)` → Invitation `(id,manuscript_id)`。**round/version/reviewer 从不可变 invitation 派生**，首版不重复三个可矛盾的外键字段。若 root 为查询加冗余列，则必须用更宽 parent UNIQUE + compound FK/触发器保证它们同时一致，不能只有各自 ID FK。
- 接受确认时才创建 draft 与 reviewer Assignment。`author_text` 与 `editor_private_text` 必须分列；`answers_json` 是按已冻结表单严格验证、有固定 key/类型/长度/必填/visibility 的有限内容，不允许模型传权限、状态、收件人或最终决定。
- v0.1 可把固定表单直接放在 Round/Report 快照，暂不建模板编辑器和通用 Answer 表。快照包含 stable question key、题目文本、kind、choices、required、order、audience(author|editor_only)；Report.form_digest 必须等于轮次固定表单。不能只保存一个指向随时可改模板的 FK；Janeway inherited BaseReviewFormElement 字段不在其静态子类本地字段列表中，不能误以为 FrozenReviewFormElement 只有两个字段。
- 提交必须独立审核页人类确认完整报告/推荐/COI/表单/附件摘要，prepared draft 本身不计入完成数；submitted 后 UPDATE/DELETE/TRUNCATE 拒绝。取消的未交草稿可改为 withdrawn 并封存，不伪写 submitted_at；不重置已提交报告回 draft。更正需未来独立追加 amendment 或新轮报告，不覆盖原文。
- 后端报告目标只计入当前轮、本轮 invitation、有效无冲突接受、已人类提交的有效报告；首版同轮每 reviewer 最多一份。编辑“已读/已考虑”以后若需要单独建事实，不把它混成 reviewer submitted。

### EditorialDecision：只有主编确认才能产生的决定事实

- 最小字段：`id, manuscript_id, journal_id, version_id, step_run_id, basis_round_id?, recommendation_confirmation_id?, reassessment_confirmation_id?, decision_code(request_revision|accept|reject), revision_kind(minor|major|null), rationale_private, author_letter, policy_version, chief_id, human_confirmation_id, decided_at, payload_digest`。
- 此表只插入已确认事实，不存模型/编辑草稿。编辑推荐直接复用现有 `ActionProposal(action_type='recommend_decision') + HumanConfirmation + completed StepRun`，其 typed 建议快照包含本次 version、basis round/report digests、推荐 code、给主编的依据、候选作者信。它只完成编辑推荐步骤并创建主编任务；**不创建 EditorialDecision、不改 accepted/rejected**。首版无需再建一份与 Proposal/StepRun 重复的 EditorialRecommendation 真值表；后续有统计/复杂评议需求再规范化。
- `UNIQUE(human_confirmation_id)`；版本/步骤/推荐和复核 confirmation 都要求 same-manuscript；主编确认摘要、当前版本/revision/policy、独立负责人/COI、有效前置步骤，且决定类型与当前关口一致。`chief_scope` 的 early reject 与评审后的 reject 要有各自允许的前置证据，不准通用 enum 直接任意跨阶段执行。
- **重要：`basis_round_id` 只做 same-manuscript FK，不强制其 version_id 等于 decision.version_id。**minor修回V2可以由编辑复核后直接交主编，依据R1(V1)旧报告；这时必须额外存在已确认 RevisionRequest(base V1,submitted V2) + 指向V2的 reassessment confirmation 链。没有这条链，跨版证据拒绝。Invitation/RoundFile 的版本仍必须严格等于本轮版本。
- `revision_kind` 仅在 decision_code=request_revision 时可非空且必须填写；accept 固定真实 `accepted_version_id=version_id`，reject 只由此确认路径产生。决定行不可改删；重新考虑是新增明确事件/决定，而非修改旧行。Agent registry 永远没有 finalize_decision 或确认工具。

### DecisionReportRelease：作者读取的匿名发布快照

- 字段：`id, manuscript_id, decision_id, report_id, ordinal, author_snapshot(JSONB), snapshot_digest, created_at`。快照只含批准给作者的 author_text、author audience 的题目/答案、允许的匿名附件名/摘要；不含原始私密答案、reviewer_id、invitation_id、邮箱、COI文本或文件上传者。
- `UNIQUE(decision_id,report_id)`、`UNIQUE(decision_id,ordinal)`；decision/report 均用 `(id,manuscript_id)` compound FK，RESTRICT 删除；报告必须已提交且位于该决定明确证据链中的本稿轮次。快照 immutable，与主编决定/确认/审计同事务创建；首版不支持任意独立“自动分享”开关。
- 不给原始 Report 表加一个 `visible_to_author=true` 就向作者序列化整行。作者通过专用 release projection/API 读取批准快照；原始 report endpoint 对作者始终拒绝，即使有 release。这样不会因未来 serializer 新加一个字段意外公开 reviewer/私密评论。
- 决定可以选择不分享任何报告；未分享时作者连 report ID、私密推荐、附件下载路径都拿不到。审稿人同意公开、已交稿、编辑已读都不自动等于 release；公开评审不在v0.1。
- 不能把审稿人自由文本中的自报姓名视为已经自动匿名；结构隔离保护元数据，文本/附件仍需负责人的实际审核。初期只用合成材料，不声称已解决任意文档的隐私净化。

### RevisionRequest：决定与新版本之间的明确链

- 字段：`id, manuscript_id, journal_id, decision_id, request_no>=1, base_version_id, draft_version_id?, submitted_version_id?, kind(minor|major), rereview_required, author_instructions, due_at, status(requested|submitted|cancelled), requested_at, submitted_at?, author_confirmation_id?`。
- `UNIQUE(decision_id)`、`UNIQUE(manuscript_id,request_no)`、`UNIQUE(id,manuscript_id)`；`UNIQUE(manuscript_id) WHERE status='requested'`，避免两个并行开放修回请求；decision/base/draft/submitted version 和确认都 same-manuscript。base 必须等于 request_revision 决定的 version；submitted 必须是不同的新冻结版本，不能复用/覆盖原版。
- 请求由主编 request_revision 的同一事务创建，instructions/due/kind/rereview策略进入当次不可变确认快照。作者新草稿可复用旧标题/作者/机构/文件来源，但所有修改为新行，原冻结 VersionFile 不覆盖；需要当前作者重新确认的声明不能由AI复制成“已勾选”。可保留旧声明只读参考，当前稿标未确认。
- 保存作者 response_letter/逐条回应可放新版本受控 metadata（有固定 schema）或另建短 RevisionResponse；首版选一个唯一真值来源，不在 request 和 version 复制两份可独立编辑内容。提交后快照包含正文、作者、回应与文件摘要，通过人类确认才写 submitted_version_id/author_confirmation_id/submitted_at 和 status=submitted。
- requested 的目标/责任/期限不随意改写；需要延期后续设计显式人类批准的 amendment 事件。submitted/cancelled 终态不可删改。作者完成提交不等于编辑复核完成，更不等于主编录用。

## 3. 现有 Assignment / WorkItem 必须配套收紧

**reviewer grant 只在接受后产生。**当前 Assignment capability enum 没有 reviewer，需要正式扩展；建议增加 `review_invitation_id?` 同稿 FK，并用 CHECK 约束 reviewer capability 必须有该 typed target、其他旧 capability 不使用它。pending 阶段允许查询“给我的邀请摘要”是独立狭窄 policy，不是稿件读权限。接受时同事务插 reviewer Assignment、Report draft、报告 WorkItem、响应 HumanConfirmation、审计与幂等回执。取消/轮次关闭结束 grant，文件下载/报告保存/模型上下文每次重新检查；历史自己的已提交报告可有专用只读投影，但不能凭此下载后来的稿件版本。

**现有 `WorkItem UNIQUE(step_run_id,kind,assignee_id)` 会阻止再次邀请生成新任务。**不能重置旧完成行或把 attempt 编进 kind 规避约束。建议增加 typed `review_invitation_id?` / `review_report_id?` 同稿 FK，二者互斥；旧唯一改成二者均 NULL 的 partial UNIQUE，另建 `(review_invitation_id,kind,assignee_id)` 和 `(review_report_id,kind,assignee_id)` 的 partial UNIQUE。邀请响应任务与报告提交任务各自生命周期；同一全局轮次步骤可有并行任务，明确它们是否仍为当前阻塞条件。

typed WorkItem 的 version/assignee 必须与 invitation 或 report 派生的版本/收件人一致；两个同稿FK只能保证“同稿”，不能保证“同一个目标版本或负责人”，需要更宽复合键或触发器补足。

全局 primary stage 与并行任务不能互相覆盖：0个有效接受时显示“寻找审稿人”；有人接受后显示“同行评审/等待报告”；达到 required_reports 后允许编辑准备汇总，未响应者不伪造完成。余下 pending/accepted attempt 要由负责人明确取消或按政策关闭并保留历史；主编决定的完整审核快照应列出本次关闭/取消的邀请与待办及原因，不能在确认后额外暗加副作用；不能仅因一个人提交报告就把所有待办完成。所有这些都是后端规则，模型只解释当前投影。

## 4. 关系和不变量的精确落点

| 边界 | DB 保证 | 同一 Action Gateway 事务中的确定性复核 |
| --- | --- | --- |
| 邀请属于哪一轮/版本 | Invitation 的 round/manuscript/version triple FK；FK到本稿/本刊 | 当前轮 open、既定盲稿集及真实文件哈希；actor 有 handling_editor 本稿有效分派，无作者COI |
| 一个人同轮再次被邀请 | attempt_no UNIQUE + pending/accepted partial UNIQUE；身份/内容不可变 | 锁 round 后分配 attempt；只有旧attempt terminal无报告时可新建；同请求重试返原回执 |
| 接受与访问 | status/timestamp CHECK；reviewer Assignment 关联 invitation；终态 transition trigger | 本人、会话/期刊、截止时间、无已知COI且明确声明none；接受前文件/正文/模型检索均拒绝 |
| 报告与表单 | invitation UNIQUE；同稿 FK；submitted不可变；digest/confirmation非空成对 | 接受/有效 grant/轮次/版本/表单digest匹配；完整必填typed答案；真实附件读取和hash；独立人类确认 |
| 数量门槛 | required_reports范围及打开后不可改；同轮同reviewer有效占位 | 只计当前轮submitted有效报告；不计邀请accepted或draft；旧轮报告不直接充抵新轮目标 |
| 作者看到什么 | Release 强FK/唯一顺序/不可变快照；原Report不赋作者访问 | 本稿作者会话、存在主编确认的对应decision/release；只读匿名allowlist DTO，绝不“先全量取再前端隐藏” |
| 编辑与主编 | 建议确认存现有immutable Proposal/Confirmation/Step；Decision有独立human_confirmation UNIQUE | 主编才可 accept/reject/request_revision；复核当前version/revision/policy/assignment/COI，不能直接信任建议或LLM输出 |
| 修回与决定版本 | RevisionRequest强FK、新旧版本不同；open请求partial UNIQUE；新版本冻结 | minor允许旧轮证据+本次V2复核链；major新Round固定V2；接受固定真正决定的版本，制作不能悄悄拿最新草稿 |

不能只用简单 CHECK 去查询另一张表的行；same version/状态迁移/确认和文件可见性等跨表条件用 compound FK 或带 parent 锁的触发器 + gateway 双层检查。插入后改变旧 parent 的 version/target 也必须禁止，否则单次 insert 检查形同虚设。FK 默认 RESTRICT，历史/确认/文件/报告不级联删除。涉及多记录状态同事务变更时，可用明确排序的行锁或必要的 deferred constraint trigger，避免中间状态误报；不能为了方便关掉触发器。

锁顺序建议统一为 `request幂等锁 → Manuscript/Workflow → Round → Invitation → Report → Proposal/Confirmation`；所有准备快照都在最终人类确认时重查 revision/assignment/evidence digest。confirmation FK本身只证明“有这条同稿确认”，不能证明确认的是当前动作。数据库guard还应核对 proposal.action_type、typed target、version、完整payload/evidence摘要、prepared_by及responsible_user；不能拿作者投稿确认去创建接受邀请grant，或拿报告提交确认当主编决定。审稿接受的确认还需与实际reviewer本人、COI声明及原invitation一致。

确认与业务写入、grant/待办变化、审计、回执同事务；失败回滚，拒绝审计另行记录。修改/取消/重新分派使旧 proposal superseded，不能沿用旧审批。邀请响应、报告正式提交、轮次关闭等会影响决定证据/待办副作用的变化，也必须更新相关 revision 并使旧准备失效；报告私有草稿可用自身 revision，不计入正式证据。并行投稿冲突返回409时保留用户草稿，不能悄悄覆盖或替人确认。

## 5. 版本、轮次与修回的具体例子

1. **V1/R1**：作者已确认冻结V1；负责人确认打开R1，固定V1盲稿/表单。向A发attempt1，A拒绝只关闭该邀请；稿件仍找审稿人，不是退稿。明确再次邀请A时创建attempt2，旧拒绝记录仍在。A接受无冲突后才可下载R1固定材料。
2. **报告提交**：A提交Report1，原文/私密意见/题目快照冻结，作者仍不可读。编辑汇总建议只进入主编待办。主编 request_revision 时选择释放匿名作者意见；只产生被选报告的release快照，私密意见/身份不进入作者上下文。
3. **minor修回V2**：RevisionRequest.base=V1，作者修改新草稿并独立确认冻结V2。R1仍指向V1，Report1不改；编辑确认对V2的 reassessment，主编可基于R1+此复核确认accept V2，不要求空造R2。Decision.version=V2、basis_round=R1(V1)通过明确修回链解释，不能只用一个“同版round FK”误拒合法流程。
4. **major重审V2/R2**：旧R1关闭并保留原文件/报告/邀请事实；主编修回策略或负责人明确的重审确认创建R2(version=V2)。即使邀请同一A，也创建R2新的attempt、grant和Report2；R1的accepted不授予R2读权限，Report1不能算进R2完成数量。
5. **再次修回V3**：新request_no、新version_no；是否R3由本次人类决定的策略选择，不能把版本号、轮次和修回次数强制相等。每次被决定和被制作的版本都可回溯到确切确认摘要。

## 6. 同一个受控投影服务供 UI、下载和模型使用

| 当前身份/事实 | 可读 | 必须隐藏/拒绝 |
| --- | --- | --- |
| pending邀请本人 | 匿名标题/摘要、主题范围、工作量、响应/评审期限、本人邀请与响应入口；自述COI | 全文、作者/共同作者/机构/邮箱/原文件名、其他reviewer与报告、私密编辑记录；不可用直接file ID绕过 |
| accepted + active reviewer grant + open轮次 + 无COI本人 | 本轮固定匿名元数据/文件、本人报告草稿/提交确认快照；结束后按政策只读本人历史报告 | 其他轮次新文件、作者身份、其他reviewer/原始报告、编辑私密稿件元数据；reviewer角色本身不授予本稿范围 |
| handling editor本稿有效分派 | 该稿授权完整材料、邀请身份/COI、报告及私密意见、建议准备入口 | 他刊/未分派稿；主编最终确认能力；本人成为作者时自审 |
| chief本稿责任 | 全部本稿决定证据、编辑建议、选择匿名release、独立决定确认 | 越期刊/作者自审；发送邮件；把模型的一句话当确认 |
| 本稿作者 | 本人稿件版本/声明/修回任务；已确认主编决定信与已发布匿名report快照 | 未分享报告/其存在ID、reviewer身份、COI、私密答案/意见、原始附件和内部审计/建议；报告提交不自动开放 |
| production本稿分派 | 已接受的确切版本和制作所需已批准材料 | 默认不开放reviewer身份/私密评审，制作角色不继承编辑全文权限 |

模型只接收同一role/object projection；不直接把ORM `. __dict__`、完整Snapshot或fixture全集作为context。ChatTurn保留当时的受控上下文，用户切换角色/分派撤销后新回合重验，旧会话读取也不能跨用户/期刊泄露。模型消息、日志、引用id、文件URL、下载Content-Disposition、错误提示以及搜索结果均属于这个边界。匿名化必须在后端发生，不靠CSS隐藏。作者侧历史/时间线也使用单独的去身份事件投影，不能直接展示完整审计 details/actor_id 而绕过报告匿名性。

## 7. root 需要完成的验证清单（均为待验收）

- D：真实两名合成 reviewer、多个attempt；拒绝/过期/取消不改稿件reject；pending只看邀请摘要；伪造另一人的响应、跨期刊/稿/轮次文件下载拒绝；接受并声明none后才有真实grant/报告待办。
- D：Round打开后原版本/文件/表单/目标数不可改；直接SQL跨版本链接拒绝；当前版本变化不影响旧轮材料；原作者文件名/署名/私密字段不出现在reviewer API/模型/下载头。
- D：报告草稿不计数；负责人逐份确认提交，旧修订/旧表单/附件hash/已取消grant/并发请求冲突；submitted原文、私密分区、题目快照禁改删/TRUNCATE；达标只进入编辑建议，不能自动决定。
- E：author对所有未释放report列表/详情/附件/模型检索均拒绝；release仅包含被主编批准的作者可见答案及匿名文件；编辑私密意见、reviewer姓名/ID/邮箱/COI在这些投影中均不存在。
- E：编辑recommend_reject不会创建主编reject；非主编/模型确认被拒；主编决定绑定完整版本/政策/建议/报告与release快照，内容变化审批失效；重复请求同内容幂等，换内容409，失败无半完成。
- E：minor V2不必R2但必须有V1→V2修回+V2 reassessment链；major R2固定V2，旧R1报告不计新目标；旧版保留，accepted_version明确；作者提交新文件不自动完成修回或录用。
- 真实浏览器按账号响应/提交/确认，刷新仍恢复；API/DB并发/回滚与既有回归全部通过才可称切片完成。全程站内合成数据，EMAIL_SEND_ENABLED=false，不发任何真实邮件，不正式发布。

## 8. 追加核对的来源追溯与限制

既有固定快照/清单见 [OJS source-manifest](../ojs/source-manifest.json)、[OJS schema-inventory](../ojs/schema-inventory.json)、[Janeway manifest](../janeway/manifest.json)、[Janeway model-fields](../janeway/model-fields.json)。OJS/PKP相关迁移/decision源码、Janeway模型/0011迁移/security摘录已在研究库保留其原许可与出处；本文为自主中文分析，没有复制运行代码。

为核实“先接受才下载”“作者报告分享”“新轮与修回实际动作”，本次还静态读取已有隔离官方仓库缓存 `/tmp/publishing-janeway-research/upstream` 的完整 `src/review/views.py`、`src/review/models.py`、`src/security/decorators.py`。实际 `git rev-parse HEAD` 等于上列固定提交，没有切到main、未运行Django。这些补充的完整文件未新增入统一manifest（本任务只允许新建本文）；下表记录精确来源/哈希，不能声称当前自动门禁已核验未保存的完整views.py快照。后续研究批次如需完全离线重放，应由负责人显式新增许可快照与manifest记录，而非默默扩大本次文件范围。

| 补充固定源码 | 本地缓存SHA-256 | 来源/许可 |
| --- | --- | --- |
| [src/review/views.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/views.py) | `26767d418dae1f181a685be0a96ac06887637c2db16ba7cb42387080b18abfef` | 官方固定commit；2026-11-02核对；AGPL-3.0，未复制入运行应用 |
| [src/review/models.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/review/models.py) | `37aef5bcecd6e160acb54833736368b7b3c0606ad014e91d54e91383ac9208f0` | 官方固定commit；2026-11-02核对；AGPL-3.0，未复制入运行应用 |
| [src/security/decorators.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/security/decorators.py) | `8d9a4e091a3a1be466527f14bc865855160878f1ee2a67096c3ff7aed77d8d4e` | 官方固定commit；2026-11-02核对；AGPL-3.0，未复制入运行应用 |

文档/源码本身也有局限：Janeway支持的可变分享开关、覆盖/撤回/删除路径和PKP自动通知不符合本项目全部人类治理要求，本文明确选择更严格约束。PKP `IsRecommendation` 的 [241行](https://github.com/pkp/pkp-lib/blob/c4c0aa8c5293254ad253544aea230b1b607d5249/classes/decision/types/traits/IsRecommendation.php#L241) 还会实际发信，我们只学习推荐/决定分离，**绝不迁入其发信副作用**。原生子Agent Token/成本遥测不可用，值应为null；本次未产生供应商模型调用费用记录。
