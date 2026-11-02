# v0.1 normalized data contract — slice A/B

Reference: spec007, goals/publishing-v0.1.md and source libraries. First migration creates only actual author-intake/task/confirmation/chat foundation. Review/check/production tables are added with their slices, not a single empty mega-schema. Models below are imported from apps.api.publishing.domain.models. Reuse existing Base/uid/now. Table prefix publishing_. Strings UUID36, UTC aware timestamps, JSONB for bounded content/snapshots, explicit named constraints.

Existing Manuscript: add workflow_kind String20 NOT NULL server_default='legacy' (legacy|publishing); editor_id becomes nullable. Add UNIQUE(id,journal_id) for tenant composite FKs. Existing title/status and IDs/receipts remain; new title/status deterministic projections. Old APIs will restrict workflow_kind=legacy. Existing Membership stays compatible; no multi-role admin UI in slice A/B. Session active membership resolution is handled by lead.

All child entities with manuscript_id use FK to Manuscript; all referenced compound parents expose UNIQUE(id,manuscript_id). File tenant compound parents expose UNIQUE(id,journal_id). Use named FK constraints for cyclic pointers, use_alter where necessary. No cascade deleting frozen history/audit; restrictive defaults.

## Models and columns

### SubmissionWorkflow / publishing_workflows
manuscript_id PK/FK manuscripts.id; journal_id FK journals.id with composite FK(manuscript_id,journal_id)->manuscripts(id,journal_id); number String80; stage String50; revision Integer default0; policy_version Integer default1; current_version_id nullable; draft_version_id nullable; accepted_version_id nullable; current_step_id nullable; chief_id nullable FK users; assigned_editor_id nullable FK users; production_editor_id nullable FK users; required_reports Integer default1; is_legacy Boolean defaultFalse; submitted_at nullable; created_at/updated_at.

UNIQUE(journal_id,number); CHECK revision>=0,required_reports between1and3. Pointers reference same-manuscript version/step compound keys. stage string bounded by application enum; DB CHECK known stages from spec007 incl legacy_screening and rejected. Index(journal_id,stage,updated_at).

### ManuscriptVersion / publishing_versions
id PK; manuscript_id; version_no Integer; title String500 default''; abstract Text default''; language String20 default'zh'; article_type String60 default'research_article'; metadata_json JSONB defaultdict; content_digest String64 nullable; frozen_at nullable; created_by FK users; provenance String30 default'authored'; created_at/updated_at.
UNIQUE(id,manuscript_id), UNIQUE(manuscript_id,version_no); version_no>=1. Draft may update; once frozen forbid UPDATE/DELETE except none. Freezing update may set digest/frozen_at while old.frozen_at null. No current pointer defaults pretending legacy checks passed.

### VersionAuthor / publishing_version_authors
id PK; manuscript_id; version_id compoundFK; ordinal Integer>=0; name String200; email String254; orcid String32 nullable; affiliations JSONB defaultlist; corresponding Boolean defaultFalse; contributions JSONB defaultlist; linked_user_id nullable FK users.
UNIQUE(version_id,ordinal), UNIQUE(id,manuscript_id); partial UNIQUE(version_id) WHERE corresponding=true. Trigger blocks changes/deletion after parent version frozen. Author identity never automatically grants linked account access; owner/assignment policy separate.

### FileObject / publishing_file_objects
id PK; journal_id; uploaded_by FKusers; sha256 String64; byte_size Integer; media_type String100; storage_key String100; original_filename String255; scan_status String30 default'validated_text'; check_method String60 default'utf8_text_safety'; created_at.
UNIQUE(journal_id,sha256), UNIQUE(id,journal_id); size1..1048576; immutable. Only actual validated small UTF8 txt/md data in first slice; no AV/PDF parsing claims. Storage keys supplied by service, never user/model.

### VersionFile / publishing_version_files
id PK; manuscript_id; journal_id; version_id same-manuscript FK; file_object_id same-journal compoundFK; purpose String40 (manuscript|blinded_manuscript|response|similarity_report|proof); visibility String30 (author_editor|reviewer|production); display_name String255; created_by FKusers; created_at.
UNIQUE(id,manuscript_id), UNIQUE(version_id,purpose) for first slice single main/blind/response/proof each; compound manuscript+journal FK. Trigger blocks changes/deletion after version frozen. Replacement while draft via explicit service operation; no overwriting blob.

### Assignment / publishing_assignments
id PK; manuscript_id; journal_id same-manuscript/journal FK; user_id FK; capability String40(author|precheck|handling_editor|chief|production); assigned_by nullable FK; starts_at; ends_at nullable; reason Text default''.
UNIQUE(id,manuscript_id); partial UNIQUE(manuscript_id,user_id,capability) WHERE ends_at IS NULL; partial UNIQUE(manuscript_id) WHERE capability='handling_editor' AND ends_at IS NULL. Index(user_id,ends_at).

### StepRun / publishing_step_runs
id PK; manuscript_id; version_id nullable same-manuscriptFK; step_key String50; cycle_no Integer>=1; status String20 default'pending'(pending|completed|cancelled); policy_version Integer default1; entered_at; completed_at nullable; outcome_json JSONB defaultdict; confirmation_id nullable FK humanconfirmation.
UNIQUE(id,manuscript_id), UNIQUE(manuscript_id,step_key,cycle_no). Completed step history never reset; outcome timestamps are backend actions.

### WorkItem / publishing_work_items
id PK; manuscript_id; journal_id same-manuscriptFK; step_run_id same-manuscriptFK; version_id nullable same-manuscriptFK; kind String60; assignee_id FKusers; status String20 default'pending'(pending|waiting|completed|cancelled); due_at nullable; priority Integer default0; blocking Boolean defaultTrue; created_at; completed_at nullable; confirmation_id nullable FK.
UNIQUE(id,manuscript_id), UNIQUE(step_run_id,kind,assignee_id); Index(assignee_id,status,due_at), Index(journal_id,status,due_at). No generic objectid; later invitation/report tasks get explicit typed FK in future migration.

### FormDraft / publishing_form_drafts
id PK; manuscript_id; version_id same-manuscriptFK; owner_id FKusers; schema_key String60 default'intake'; schema_version Integer default1; revision Integer default0; base_revision Integer; data_json JSONB defaultdict; sources_json JSONB defaultdict; updated_at.
UNIQUE(version_id,schema_key,owner_id); revision>=0; data contains bounded extracted candidate provenance, not permissions or state truth. Actual version/author rows authoritative for normalized fields.

### ActionProposal / publishing_action_proposals
id PK; manuscript_id; journal_id same-manuscriptFK; work_item_id same-manuscriptFK; version_id same-manuscriptFK; action_type String60; prepared_by FKusers; responsible_user_id FKusers; base_revision Integer; policy_version Integer; payload_snapshot JSONB; evidence_digests JSONB; digest String64; created_at; expires_at; superseded_at nullable.
UNIQUE(id,manuscript_id), Index(responsible_user_id,created_at). Snapshot/action/base/version/responsible/digest immutable; only superseded_at may null->timestamp. No Agent final confirmation tool.

### HumanConfirmation / publishing_human_confirmations
id PK; manuscript_id; proposal_id same-manuscriptFK UNIQUE; responsible_user_id FK; session_hash String64 FK login_sessions.token_hash; digest String64; outcome String20(confirm|return); reason Text default''; confirmed_at.
UNIQUE(id,manuscript_id). Immutable UPDATE/DELETE block like audit/email approval. Snapshot hash and responsible actor checked server-side. FK session restrictive means session logout delete must be changed by lead to preserve confirmation provenance (store session_hash as plain digest evidence, NOT FK if session logout deletes): CHOOSE plain String64, no FK.

### ActionReceipt / publishing_action_receipts
id PK; user_id FK; journal_id FK; request_id String36; action_type String60; input_digest String64; response JSONB; created_at.
UNIQUE(user_id,journal_id,request_id). Preserve old CommandReceipt semantics unchanged.

### PublishingChatTurn / publishing_chat_turns
id PK; user_id FK; journal_id FK; manuscript_id nullable FK; request_id String36; input_digest String64; context_snapshot JSONB; response JSONB; created_at.
UNIQUE(user_id,journal_id,request_id); Index(user_id,journal_id,created_at,id). Models only see role/object-filtered repository projection. No real confidential input.

## Migration/research acceptance

Add DB immutability triggers for frozen versions/authors/versionfiles, immutable fileobjects, human confirmations, immutable proposal body. Use schema CHECKs, composite FKs and indexes, not merely application validators. Migration backfills all existing manuscripts as truthful legacy workflows/versions/authors/assignments/step/tasks; keeps UUIDs; no invented files/confirmation/check history. Capture explicit legacy provenance. Migration may use Python hashlib/uuid5 and database rows, no upstream code. Downgrade must not silently delete publishing-kind actual data (refuse when exists); legacy-only rehearsal is supported. Lead reviews and executes against isolated DB before main.
