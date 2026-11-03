# F：实际校样与鉴权本地预览

2026-11-03 F已实施并验收；最终835后端+35浏览器及真实新领域API6/6/实际浏览器通过，主服务已更新，详见PROGRESS。来源与边界见 `docs/research/library/comparison/production-preview-design.md`。不扩大成公开出版平台。

## 主链

E主编accept固定version/production负责人 → production：制作人员上传实际UTF8 txt/md校样，核对冻结录用版元数据 → 独立审核send_proof → author_proof：作者本人阅读确切文件后独立confirm_proof(approve|request_corrections) → approve进入preview_confirmation；corrections重开production（保留原包/意见，必须上传不同新文件再提包）→ 制作人员独立prepare_local_preview并确认 → preview_ready。Manuscript仍accepted，绝不published；鉴权本地预览始终标记“本地预览”，无公共路由/DOI/生产部署/邮件。

所有修改走现有run_action、稿件锁、revision、actor/assignment/COI检查、audit/receipt；每次确认绑定不可变完整proposal及实际文件hash。模型无以上最终确认工具；仅查询授权状态/建议。

## 实体（migration12e06b9c4f53已接E实施）

1. `ProofPackage` / publishing_proof_packages：id, manuscript_id, journal_id, accepted_version_id, acceptance_decision_id, package_no, file_object_id, display_name, metadata_snapshot(JSONB白名单从version_snapshot.data构造), material_digest（metadata+file/hash+acceptedversion/sourceDecision）, production_user_id, human_confirmation_id, created_at。unique稿件/package_no、confirmation、(id,manuscript_id)，同稿同刊FK。全部不可变，录用源必须accept/同版，本稿production人工send_proof确认。**不向冻结VersionFile追加校样**。
2. `ProofResponse` / publishing_proof_responses：id, manuscript_id, package_id UNIQUE, author_id, outcome approve|request_corrections, notes, human_confirmation_id UNIQUE, responded_at。same稿FK、不可变。原投稿作者本人confirm_proof确认，包/version/hash/元数据绑定；corrections notes>=20。approve不能仅凭聊天候选产生。
3. `PublicationPreview` / publishing_publication_previews：id, manuscript_id, journal_id, accepted_version_id, package_id UNIQUE, proof_response_id, metadata_snapshot JSONB, file_object_id, display_name, content_digest, production_user_id, human_confirmation_id UNIQUE, created_at。全部不可变，同稿/同版，response必须approve且同包，元数据/file精确等于包；production人工prepare_local_preview确认。本地预览不是公开Publication，后续正式出版另立模型/授权流程。

制作上传仍用现有FileObject/CAS和严格文件校验，另有私人FormDraft(schema_key=production_proof、owner=当前制作人、version=acceptedversion)保存当前待审file引用/filename/hash；该草稿不是正式ProofPackage。上传改动bump稿件revision使旧proposal失效；已发出的包不变。下载统一策略与实际CAS验证，production/author可见适合自己的确切包，原reviewer grant/邀请不足以见校样/预览。

## 输入与冻结payload

`send_proof` 输入 `{declarations:{metadata_reviewed:true,proof_reviewed:true}}`：须严格布尔，不接受1或字符串。payload.proof_package=`{id,accepted_version_id,acceptance_decision_id,package_no,file:{id,filename,sha256,byte_size,media_type},metadata_snapshot,material_digest,production_user_id}`。准备不落正式Package；confirm重验文件实际bytes与整个投影，写Package并转作者待办。

`confirm_proof` 输入 `{package_id,outcome:'approve'|'request_corrections',notes:'',declarations:{proof_reviewed:true}}`；corrections notes>=20。payload.proof_response=`{id,package_id,accepted_version_id,outcome,notes,declarations,package_digest}`；包完整快照在payload.proof_package。独立审核可下载本包，不默认选择结果或声明。

`prepare_local_preview` 输入 `{declarations:{metadata_reviewed:true,approved_proof_reviewed:true}}`；payload.preview=`{id,accepted_version_id,package_id,proof_response_id,metadata_snapshot,file:{id,filename,sha256,byte_size,media_type},content_digest,production_user_id,local_only:true}`。Package与Response完整摘要同页可见；仅绑定作者approve包。确认建立Preview+stage preview_ready，原statusaccepted。

## 接口与UI（实施前冻结精确合同）

制作上传 `POST /manuscripts/{id}/proof-files` request_id/expected_revision/file(purpose=proof)；实际下载 `/proof-packages/{id}/file`，本地预览DTO `GET /previews/{id}`，路由 `/publishing/preview/{id}`复用三栏常驻对话shell，不使用dangerouslySetInnerHTML。DTO只含冻结公开形元数据/校样text与鉴权状态，不含内部决定/报告/私密文件。匿名未登录401、仅历史reviewer404、跨刊404。

submission新增production投影，由实际角色/阶段给出current draft/file、本稿历史包及作者响应、最终preview link；作者不见制作人的私人草稿但能看已send包。production不见E私密评审或内部决定理由。visibility_scope新增production_private按当前实际grant收窄模型/history/replay；文件工具若扩展必须显式白名单，不能从同version推测访问。

验收包括完整同篇五角色browser链、作者要求更正→第二包、preview鉴权/转义/hash、模型无确认/公开发布工具、immutable/sameversion/human-binding PG约束、旧数据迁移回归和scripts/verify.sh。E/F完成后再进行新领域真实DeepSeek安全调用，保留旧基线并备份主库，不能因无host key把已运行live服务重建成Mock。

## 冻结UI/API补充合同

ProductionMetadata=`{schema_version:1,title,abstract,language,article_type,keywords,authors:[{name,orcid,affiliations,corresponding,contributions}],funding_statement}`。只从accepted版生成，不含email/linked_user_id/作者声明/内部伦理或COI字段。此片校样更正仅正文，不支持结构化题名/署名更正；界面明确说明，不假装上传文件就修改冻结元数据。

ProofFileDTO=`{id,filename,sha256,byte_size,media_type,check_method:'utf8_text_safety',scan_status:'validated_text',download_url}`；id为FileObject而不是VersionFile，filename来自本稿绑定，不读去重blob的original_filename。ProofResponseDTO=`{id,package_id,outcome,notes,package_digest,responded_at}`，其中package_digest可从不可变提案/包派生，无需重复物理列。ProofPackageDTO=`{id,accepted_version_id,acceptance_decision_id,package_no,file,metadata_snapshot,material_digest,created_at,response:null|ProofResponseDTO}`。PreviewLinkDTO=`{id,url,content_digest,created_at,local_only:true}`。

Detail.production=`null | ProductionBase & ({mode:'production',can_upload_proof:boolean,draft_file:null|ProofFileDTO}|{mode:'author'})`；ProductionBase=`{accepted_version_id,acceptance_decision_id,metadata_snapshot,metadata_digest,active_package_id,packages:ProofPackageDTO[],preview:null|PreviewLinkDTO}`。包按package_no升序。作者完全不含draft_file；active_package_id由当前StepRun.outcome_json绑定，不能靠max(created_at)或最新上传文件决定。production/author仅实际授权；其他staff可读取安全预览但本片不提供制作表单投影。

PreviewDTO=`{id,manuscript_id,number,accepted_version_id,package_id,proof_response_id,metadata_snapshot,file,text,content_digest,created_at,proof_approved_at,local_only:true,formally_published:false,manuscript_status:'accepted'}`。text从实际CAS读取并复核，React纯文本转义。独立预览路由用后端返回manuscript_id设定对话上下文，不能信任伪造query。File download_url不参与摘要。

新增GET `/manuscripts/{mid}/proof-files/{fileObjectId}`只允许当前制作人自己FormDraft绑定的实际文件；作者/同稿其他人404。Package正式下载 `/proof-packages/{packageId}/file`。私人上传与已send包权限不同。历史包对作者及仍有实际授权的production/handling/chief无COI可读，历史reviewer邀请不足以授权。production角色的通用VersionFile下载仅限accepted版的manuscript文件；不能猜ID下载旧稿/修回回复/私密复核报告。

三类F提案payload.version=null（制作用公开形metadata，不外泄投稿声明/作者邮箱），但ActionProposal.version_id仍指真实accepted版，包/响应/预览中的accepted_version_id与flow强绑定。完整F快照单独显示，不能通过通用作者Intake Snapshot混入内部元数据。metadata/file摘要按规范化安全对象计算，不包含URL。

约束补强：ProofPackage UNIQUE(id,manuscript_id,accepted_version_id)，ProofResponse UNIQUE(id,manuscript_id,package_id)，Preview复合FK同时绑定package/version及response/package；服务及触发器精确对比同包approve响应、文件和metadata。校样corrections后新hash只与上一个被要求更正包比较，允许将来合法恢复更早内容。确认标签：确认交作者校样 / 确认通过本包校样 / 确认要求校样更正 / 确认生成鉴权本地预览。模型没有这些确认或人工声明工具。

production mode额外含 `accepted_materials:VersionFileDTO[]`，只accepted版purpose=manuscript；其字段沿已有VersionFile（id为VersionFile、name、sha256等），与ProofFile（id为FileObject、filename）分开。production角色generic detail.version=null、versions仅accepted摘要，field_sources/return_request/staff_review/review/editorial清空；timeline仅安全步骤标签，不泄露原私密payload。F frozen payload.file严格5键 `{id,filename,sha256,byte_size,media_type}`，另顶层 `proof_download_url` 供独立审核实际下载，不入内容摘要；DTO派生check/scan/URL。F当前制作授权按实际grant/task/COI，不永久锁死旧accept人员，send确认同步flow.production_editor_id到实际负责人。
