# E：决定、匿名反馈与正式修回

状态：2026-11-03 E检查点已验收，完整686后端+24浏览器通过；证据见PROGRESS，F及整个Goal仍未完成。依据 `docs/research/library/comparison/review-revision-design.md` 的 OJS 固定轮次与 Janeway 决定/修回分离；不是上游数据库复制。

## 业务与权限

D closed round → editor_recommendation（责任编辑本人确认建议）→ chief_decision（本稿已分派主编本人确认）→ request_revision / accept / reject。建议和审稿人推荐不是决定。所有操作用现有提案、独立审核页、HumanConfirmation、事务锁、幂等回执及审计。LLM无最终确认工具。

request_revision 同事务建立 RevisionRequest 与新作者草稿、author_revision 待办。作者修改资料/文件、重新回答声明、上传实际 response 文件后，独立确认 submit_revision；冻结新版本，完成请求，生成责任编辑 revision_assessment。minor 可经人工 ready_for_chief 进入本版本 editor_recommendation；major 必须人工确认匿名材料后 rereview，进入 reviewer_selection 开新轮。每个版本重新编辑建议/主编决定。accept 设置 accepted_version_id 并转 production；reject 结束于 rejected。都不发信、不公开发布。生产负责人必须是无作者冲突的实际 production_editor 成员。

minor 可引用旧版本的已关闭评审轮，但必须有连续的正式修回请求、当前版本人工复核和当前版本编辑建议证明。V3 的来源决定可以基于 R1(V1)，不能错误要求 V3 的 base V2 等于轮次 V1。major 不允许此桥接，须当前版本的新轮报告。原稿、旧报告、旧确认不可改。

## 规范化实体

新增 `decision_models.py`，在 domain/__init__ 注册；迁移跟随10c84f7a2d31。

1. `EditorialDecision` / publishing_editorial_decisions：id, manuscript_id, journal_id, version_id, step_run_id, basis_round_id, recommendation_confirmation_id, reassessment_confirmation_id nullable, decision_code(request_revision|accept|reject), revision_kind(minor|major|null), rationale_private, author_letter, policy_version, chief_id, human_confirmation_id, decided_at, payload_digest。同稿复合FK；unique confirmation、step、(id,manuscript_id)。不可变。basis_round不强制同version。FK到实际完成当前版本 recommend_decision 提案的确认；跨版本要求有效 reassessment。chief human确认必须是 record_decision 且精确绑定当前任务/稿件/版本/载荷。原文不写通用audit。

2. `DecisionReportRelease` / publishing_decision_report_releases：id, manuscript_id, decision_id, report_id, ordinal, author_snapshot JSONB, snapshot_digest, created_at。同稿FK、unique(decision,report)/(decision,ordinal)，不可变。仅该决定basis_round已submitted报告。author_snapshot严格 `{author_text, answers, questions}`：answers仅原表单audience=author题目，questions仅相同题目的key/prompt/type等安全固定定义；不含推荐、私密文本、审稿人身份/邮件/COI。chief确认的public_reports精确绑定这些快照/顺序/摘要。作者DTO不暴露raw report_id或reviewer_id，不能由release获得原始报告下载/查询权限。

3. `RevisionRequest` / publishing_revision_requests：id, manuscript_id, journal_id, decision_id UNIQUE, request_no(每稿递增), base_version_id, draft_version_id, submitted_version_id nullable, kind minor|major, rereview_required bool, author_instructions, due_at, status requested|submitted, requested_at, submitted_at nullable, author_confirmation_id nullable。同稿FK，partial unique稿件requested。除requested→submitted字段外不可变，终态不可变。提交绑定 submit_revision 提案及准确新冻结版本，需实际response文件；major始终rereview_required。请求与草稿创建在同一人类决定事务。不要FK到session（注销不破坏历史）。

## 冻结提案载荷合同

公共 envelope 沿用 action/stage/version/schema_version/synthetic_only + evidence。版本为完整授权快照，prepared只产生提案，不产生决定/修回请求。以下值由后端生成/验证，客户端不能指定身份/历史依据。

`recommend_decision` 数据输入：`{recommendation:request_revision|accept|reject,revision_kind:minor|major|null,rationale_private:min20,max8000,author_letter:min20,max12000}`；仅request_revision有kind。payload.recommendation：`{version_id,basis_round_id,recommendation,revision_kind,rationale_private,author_letter,report_digests:[{report_id,content_digest,form_digest}],reassessment_confirmation_id}`。

`record_decision` 输入：`{decision_code,revision_kind,rationale_private,author_letter,share_report_ids:UUID[],author_instructions:'',due_days:null|1..90}`。request_revision要求kind、instructions>=20、due_days；accept/reject禁止kind/instructions/due。不默认选择决定。payload.decision：`{id,version_id,basis_round_id,recommendation_confirmation_id,reassessment_confirmation_id,decision_code,revision_kind,rationale_private,author_letter,policy_version,public_reports:[{report_id,ordinal,author_snapshot,snapshot_digest}],revision_request:null|{id,decision_id,request_no,base_version_id,planned_draft_version_id,kind,rereview_required,author_instructions,due_at}}`。另 payload.decision_digest=core.digest(payload.decision)，Decision.payload_digest 等于该值。Confirmation.digest仍绑定完整envelope。

`submit_revision` 输入空对象，payload.revision_request：`{id,decision_id,base_version_id,draft_version_id,kind,rereview_required,author_instructions,due_at,submitted_version_id}`；加完整新版本快照/文件hash。prepared必须资料和声明完整并有response文件；确认重新验证bytes。新稿首次/预审退回仍用旧submit，不受此合同影响。

`assess_revision` 输入：`{outcome:ready_for_chief|rereview,notes:min20,max8000,declarations:{reviewed_current_version:true,reviewed_response:true,anonymous_material_reviewed:boolean}}`。major仅rereview且anonymous_material_reviewed=true；minor rereview也需匿名材料确认。payload.assessment：`{revision_request_id,version_id,outcome,notes,declarations,base_version_id,response_file:{id,sha256},basis_round_id}`。用现有提案/确认/StepRun，不另造复核表。

补充：record_decision输入与payload.decision均保留 `share_reports_anonymity_reviewed` 默认false，有分享报告时必须由主编勾选true。白名单字段不能保证自由正文匿名，须看完整拟共享内容。payload.decision另含 `production_assignee:null|{id,name,email,role:'production_editor'}`；录用prepare固定，confirm重验同人，不能临时替换。主编可改变编辑建议的code和正文，建议只作前置依据。

DB约束应校验必要字段/同稿/不可变/动作与确认关系；复杂跨版本归纳链由确定性服务逐步验证到本轮version+测试负责，不能用LLM。并发同请求不重复决定/版本/请求/待办，旧版本/角色/修订变化全部失效。

## 投影与UI

submission新增 `editorial`，仅本稿handling/chief无冲突者得 staff原文/建议和submitted原始报告；作者只得 `feedback`（decision_id,decision_code,author_letter,revision_kind,instructions,due_at, reports序号+安全snapshot），当前requested revision_request供本人完成；审稿人维持原DTO不见决定私密内容。visibility_scope新增editorial_private并参与模型/history/replay子集检查。列表只能安全摘要，不带私密内容。

右侧组件追加editor_recommendation/chief_decision/author_revision/revision_assessment真实表单；中间对话继续常驻。编辑建议可看submitted报告，主编审核显示完整决定信、明确勾选共享的匿名意见/内容、修回要求和截止时间。作者显示正式反馈、response上传缺项和新版本资料。所有最终确认在现有独立审核路由；输入框不默认选关键结论/不代勾声明。

模型本片先读取授权feedback/当前版本、准备已填写资料的审核；不能生成决定枚举、勾人工声明或直接确认。AI候选可以在后续扩展，先保证全流程实际操作和权限。

## 验收

真实PG模型约束/迁移漂移；服务minor两次修回链、major新轮、reject、accept及生产移交；作者不见私密报告/身份、审稿人不见决定、非负责人/作者冲突403、准备不落决定、确认绑定/变更失效、并发/幂等；同篇浏览器D→编辑建议→主编request_revision+分享→作者V2/声明/response→编辑复核→建议→主编accept。完整scripts/verify.sh；本片通过不等于F/Goal完成。
