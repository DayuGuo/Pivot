# Publishing OS v0.1 implementation contract

Goal contract: goals/publishing-v0.1.md. The bounded local implementation is now accepted (835 backend+35 browser; real new-domain API6/6 and actual browser). Exact review/decision/production contracts are refined by specs008/009/010; this is not production readiness or public publication. Research root docs/research/library/: OJS3.5.0-6/PKP pinned dependency, Janeway1.8.4, static source manifests/field dictionaries and current-code audit. Consult both upstream analyses at each milestone and append decisions/acceptance evidence.

## Incremental architecture

Keep existing Manuscript UUID as stable submission identity. Add `workflow_kind` default legacy and allow editor_id nullable for new author drafts. Legacy APIs/commands keep their receipt digests and behavior and are explicitly limited to legacy records, so their broad editor visibility cannot bypass the new object policy. New APIs under `/api/publishing`, real UI under `/publishing`; old `/workbench` remains clearly a fixture demo. Normalized child tables use `publishing_` prefix and reference the actual Manuscript, not copied fixture IDs. Backfill existing records as legacy_screening with truthful incomplete legacy metadata; never fabricate checks, files or human confirmations.

The one-to-one SubmissionWorkflow is the canonical current workflow/number/version/step/revision projection. Manuscript.title/status remain deterministic compatibility projections. Phase/current step, work-item state and review counters are separate facts. Do not turn demo user JSONB into shared publication state.

v0.1 has five test roles: author, editor (precheck staff and handling editor when assigned), chief_editor, reviewer, production_editor. Keep the legacy Membership uniqueness initially; optional child MembershipRole grants can extend one journal membership to multiple explicit roles without duplicating the primary role. Resolve the session's working membership deterministically (explicit journal/role selection when ambiguous), not arbitrary first row. All publishing access requires journal+ownership/active assignment+stage+COI. Author-approver conflicts are rejected. No production deployment or real mail.

## Shared normalized entities

Use SQLAlchemy Base/uid/now from existing models. UUID IDs String36, UTC DateTime(timezone=True), JSONB only for typed metadata/form content/snapshots; core relations/roles/states/timestamps relational. Child tables carry manuscript_id, composite `(id,manuscript_id)` unique parent keys/FKs prevent cross-manuscript joins. Journal parents similarly protect files/assignments. Use named constraints and indexes. Exact columns in data-contract.md; no runtime dependency on upstream code.

- SubmissionWorkflow: one per manuscript, uniquejournal+number, canonical stage/revision, current/draft/accepted version and current step pointers, assigned editor/chief/production users, legacy flag, policy version, report target and timestamps.
- ManuscriptVersion, VersionAuthor, FileObject, VersionFile: draft editable; human-confirmed submission freezes exact metadata, ordered authors and content-addressed file hashes. Historical profile changes cannot alter署名. Files initially small UTF8 .txt/.md only; byte/type/size checks are honest text safety checks, not virus scan/PDF parsing. Private CAS storage is durable and authorization gated.
- Assignment, StepRun, WorkItem, CheckRun: real responsibilities, sequential check evidence, immutable prior step outcomes. Similarity is explicitly manual report review, not invented external detection. No generic target type/id tasks.
- FormDraft/field provenance, ActionProposal, HumanConfirmation, ActionReceipt: typed draft candidates; immutable full payload/version/revision/evidence digest; independent human review/confirm route, exactly current responsible actor. Draft or file mutation, reassignment or workflow changes invalidate earlier proposal. Confirmation, workflow, tasks, audit and receipt atomic/idempotent. Final confirm absent from Agent registry.
- ReviewRound, ReviewInvitation, ReviewReport: fixed version/anonymous materials, invited/accepted/declined/report timestamps separated, author-visible/private report partitions. Invitation acceptance creates actual assignment; reviewer role alone grants nothing. Repeated rounds preserve history. Effective invitations unique without deleting old attempts.
- EditorialDecision, ProductionPackage, ProofConfirmation, PublicationPreview: recommendation separate from chief decision; accepted version fixed; author proof separate from production readiness; local authenticated preview snapshot distinct from external publication. No DOI registration.
- PublishingChatTurn: private user+journal context-bound turns and provider telemetry, role-filtered domain repository only; no fixture fallback.

## Main path and gates

`author_draft → precheck_completeness → similarity_review → technical_screening → chief_scope → assign_editor → editor_quality → reviewer_selection/peer_review → editor_recommendation → chief_decision → author_revision → revision_assessment → chief_decision → production → author_proof → preview_confirmation → preview_ready`.

Chief decision is request_revision/accept/reject, only human confirmation. Major revision may create a second review round; minor revision permits explicit editor reassessment before chief confirmation. Every named gate has its responsible work item and independent complete-payload review. Invitation response/report and parallel pending reviewers do not overwrite manuscript phase arbitrarily; round targets determine primary phase.

Intake: author supplies loose synthetic text via conversation, AI proposes only allowed metadata/authorship fields and source references. Back-end schema drives missing/conflict fields. Declarations (originality/copyright/COI/ethics applicability) never AI-written/auto-checked. Complete metadata/authors/blinded file and explicit declarations required at submit confirmation. A later version is new rows, never editing the frozen version.

Precheck actors may prepare completeness/manual similarity/anonymous-material evidence, but each pass/return human-confirmed. Chief scope+assignment precede handling editor quality assessment. Invite existing synthetic reviewer in-app only, acceptance requires that account's conflict declaration. Reports explicitly separate author text/editor-private text and freeze on human submit. Author sees report text only after chief releases it through confirmed decision; never identities/private fields.

Production actor works only on accepted assigned material; uploads proof, responsible human requests author review, author confirms exact proof digest (or returns), production confirms authenticated local preview. Changes invalidate old proof/preview preparation. Local preview prominently says not formally published and never exposes unconfirmed material publicly.

## Model and UI

Persistent three-column shell with central chat across work/material/review/preview routes; role tasks left, authorized state/version/owner/next gate right. No hidden floating-only assistant. New domain tools separately registered from fixture tools. Read projections are identical across API/UI/model; reviewer context is anonymous. Tools prepare drafts/proposals and navigate, never confirm/finalize/mail. Live provider remains explicit environment opt-in; preserve current runtime key across deploy/test, no global Codex config changes.

Independent review route under shared shell shows entire immutable snapshot, files/hash, changes/invalidity and explicit human action. Model prose cannot substitute for this route or authority. Buttons backed by real APIs/DB; all failures/409 recoverable, no fake task counts. Every role can refresh and recover persisted work.

## Acceptance

Use isolated Mock verification stack and preserve live main environment. PostgreSQL constraints, immutable triggers, legacy backfill/idempotence, journal/role/object/COI/anonymity, stale proposals, human confirmation retry/concurrency and rollback tests. Browser writes the full path through five isolated role sessions (no pre-seeded final-state fixture), verifies refresh, author/reviewer privacy, decline/return branch and local preview. Real DeepSeek tools run against synthetic domain when provider available, with exact action receipts and no final confirmation tools. Existing322 backend/23 browser baseline coverage stays.

One command startup, documented accounts/demo, source-to-field/migration/test mapping, full scripts/verify.sh success plus migration rehearsals and final peer review. Goal remains active until complete evidence, not after the first slice or research deliverables.
