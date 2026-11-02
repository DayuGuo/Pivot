# Editorial intake v1 — API contract

Same-origin browser `/api/*` proxies to FastAPI (internal routes also `/api/*`). JSON error uses `{detail: string}`. Cookie `publishing_session` is HttpOnly. Mutating authenticated requests require `X-CSRF-Token` from `/api/auth/me` or login response. Credentials and CSRF stay in memory; session cookie restores on reload.

- POST /api/auth/login `{email,password}` => `{user:{id,email,name,role},csrf_token}`
- GET /api/auth/me => same shape
- POST /api/auth/logout => `{ok:true}`
- GET /api/workspace => `{journal:{id,name},manuscripts:[{id,title,status,created_at,author_name,editor_name,task:{id,status,kind}}],messages:[{id,role,content,provider,manuscript_id,created_at}],audit:[{id,action,actor_name,entity_id,details,created_at}],email_send_enabled:false}`
- POST /api/conversations/commands `{message,request_id(UUID)}` => `{message:{...assistant message},manuscript: manuscript|null,provider:'mock'}`. Editor/chief_editor only for create+screen tool. Author/reviewer get 403. The canonical prompt is `创建一篇测试稿件，并交给编辑初筛。`. Unsupported prompts produce a persisted assistant explanation and no manuscript. Unknown or malicious model tool calls fail closed.
- GET /api/manuscripts/{id} => manuscript, access scoped by role and ownership.
- GET /api/health => `{status:'ok',database:'postgresql',email_send_enabled:false,model_provider:'mock'}`

Demo users: editor@publishing.test / EditorDemo2026!; author@publishing.test / AuthorDemo2026!; reviewer@publishing.test / ReviewerDemo2026!; chief@publishing.test / ChiefDemo2026!.

Bootstrap creates journal, users with journal membership and auditable seed events. Command creates synthetic author-owned manuscript (draft → submitted → screening), assigned editor task, conversation and audit in one transaction. Server idempotency bound to actor + request UUID + input digest. High-impact decisions are unavailable to agent. All data synthetic.
