# v0.1 A/B UI/API contract

Actual foundation API implementation in domain/api.py and core.py; test first before claiming runnable. All endpoints `/api/publishing`, same HttpOnly/CSRF convention. JSON extra fields rejected. UUID request_id on every mutation, expected_revision on edits/proposals/confirmation. Model final confirmation tools never exist.

- GET /session -> {user:{id,name,email,role},journal:{id,name},csrf_token,model:{provider,model,available,error_code?},synthetic_only:true,email_send_enabled:false}.
- GET /workspace -> {submissions:[Summary],tasks:[Task],counts:{actionable,waiting},synthetic_only:true}.
- POST /drafts {request_id,title?} -> {manuscript_id,number,revision}; creates own real draft/author/task.
- GET /manuscripts/{id} -> Summary plus {versions,version:VersionSnapshot|null,missing:[{field,message}],can_edit_intake,field_sources,timeline,allowed_actions}.
- PATCH /manuscripts/{id}/intake {request_id,expected_revision,data:IntakeData} -> {manuscript_id,revision,missing}.
- POST /manuscripts/{id}/files {request_id,expected_revision,file:{filename,content_base64,purpose}} -> {manuscript_id,revision,file_id,sha256}; file is actual bytes UTF8 txt/md max1MiB. File input→ArrayBuffer→base64, never fake filename-only upload. purpose manuscript|blinded_manuscript|response initially; controls not exposed for unsupported purposes.
- POST /manuscripts/{id}/proposals {request_id,expected_revision,action_type:'submit',data:{}} -> {proposal_id,manuscript_id,digest,review_url,requires_human_confirmation:true}. Missing info422. Creating proposal does NOT submit.
- GET /proposals/{id} -> {id,manuscript_id,number,action_type,digest,base_revision,payload:{action,stage,version:VersionSnapshot,schema_version,synthetic_only},evidence,created_at,expires_at,status:'pending'|'expired'|'confirmed',confirmation:{id,outcome,confirmed_at}|null}.
- POST /proposals/{id}/confirmations {request_id,expected_revision,digest,acknowledged:true,reason?} -> {manuscript_id,number,stage,revision,confirmation_id}; only current responsible actor, no AI call.
- GET /files/{id} -> private actual file, content-disposition and hash; relative frontend proxy link works.

Summary={id,number,title,stage,stage_label,revision,is_legacy,is_owner,capabilities:string[],current_version_id,draft_version_id,accepted_version_id,own_tasks:Task[],created_at,submitted_at}.
Task={id,manuscript_id,number,title,kind,label,status,due_at,priority,blocking,version_id}.
VersionSnapshot={id,version_no,data:IntakeData,files:VersionFile[],frozen_at,provenance}. Legacy data intentionally incomplete/read-only; check is_legacy before interpreting strictIntakeData.
VersionFile={id,purpose,visibility,name,sha256,byte_size,media_type,check_method,scan_status,download_url}.
Timeline={id,step,label,status,cycle,completed_at}.
IntakeData={title,abstract,language:'zh'|'en',article_type:'research_article',keywords:string[],authors:[{name,email,orcid:null|string,affiliations:string[],corresponding:boolean,contributions:string[]}],funding_statement,declarations:{originality:boolean,copyright:boolean,competing_interests:'unanswered'|'none'|'declared',competing_interests_text,ethics:'unanswered'|'not_applicable'|'approved',ethics_reference}}. All initial declarations false/unanswered, never automatically ticked.
allowed_actions initially [{action:'submit',label:'准备投稿审核',requires_human:true}] only when own draft task; future gates add explicit server schema fields, never hard-code fake later actions.

Chat endpoint implementation comes next, independent of fixture chat:
GET /chat -> {messages:ChatMessage[],provider}; POST /chat {request_id,message,context:{manuscript_id:null|string,version_id:null|string,scope:'case'|'journal',view:'work'|'intake'|'progress'|'review'|'preview'}} -> {request_id,messages:[user,assistant],provider,state_changed}. Each message {id,role,content,created_at,provider,context,references:[{label,manuscript_id,version_id?,file_id?,quote?}],tool_receipts:[{tool,status,manuscript_id?}],action:null|{type:'select',manuscript_id}|{type:'review',proposal_id,manuscript_id}}. Same UUID retry, no HTML from model, keep same primary conversation mounted across route changes.

UI route `/publishing` under shared client shell + context. Default right queue or selected manuscript intake/progress. Independent `/publishing/review/[proposalId]` under same layout, full read-only snapshot plus explicit human acknowledgment/confirm button. Chat remains mounted/visible. Link from old root to new real workspace; legacyfixture route still labeled demo. No unimplemented action buttons, old flows not deleted.
