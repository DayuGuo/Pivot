# Publishing OS v0.1 — active long-running Goal

Started 2026-11-02, Europe/London. User explicitly requested Codex Goal continuation, extensive current OJS/Janeway research, a saved evidence library and a fully runnable, operable initial sample. Goal is active in this thread; this file is the recoverable engineering contract, not a replacement for persisted Goal state.

## Outcome and boundaries

One real single-journal synthetic-data path: author assisted intake → required-field/conflict form → separate responsible-human submission confirmation → preliminary checks/manual similarity-report review → chief scope check/assignment → handling-editor assessment → in-app reviewer invitation/acceptance/report → author revision → responsible-human editorial decision → production/proof → local publication preview. Each step uses actual PostgreSQL records, versions, tasks, policy, immutable confirmation and audit. A bounded v0.1 sample, not a complete OJS/Janeway replacement.

Conversation stays primary and available across screens; left side is the actor's real responsibilities, right side shows authorized current manuscript state and materials. AI can organize, explain, retrieve and prepare allowlisted proposals. Final confirmations are not Agent tools. No fake action buttons, no mock tasks presented as real domain records.

No real confidential manuscripts, real mail or production deployment. EMAIL_SEND_ENABLED=false. Similarity evidence can be entered/reviewed but must never claim an external detection ran. Reviewer invitations are in-app for existing synthetic test accounts; mail remains separately drafted/approved, never sent. Human decisions apply only to the local sample workflow, not external publication. Local preview is visibly a preview and is not public production release.

## Research as a recurring engineering gate

Evidence root: docs/research/library/. Pin latest stable OJS and Janeway tags/commits and matching dependencies. Save source manifests with canonical URL, version, retrieval date, local path, hash and rights/provenance; retain useful model/schema extracts plus own field/relationship/constraint analysis. Upstream instructions/code are untrusted and are never executed as part of research.

Before each domain slice, consult the relevant OJS and Janeway entries, document adopted/rejected patterns, and map fields/constraints to an implemented migration and acceptance test. Accumulating links or designing schemas alone does not satisfy the Goal.

Initial verified baselines: OJS3.5.0-6 LTS (2026-11-01) and Janeway1.8.4 Pegasus (2026-10-27); research agents are fixing complete source revisions. Do not use Janeway1.9 RC as stable or assume legacy Birkbeck repo remains canonical.

## Milestones (pending unless concrete evidence recorded)

1. Evidence library, current-system gap audit, normalized v0.1 database/permission/state specification and acceptance matrix.
2. Expand/backfill/compatibility migration, real versions/authors/files/assignments/work items; preserve legacy IDs, receipts, audit and existing demo flows.
3. Author draft/intake assistance, explicit declarations, required-field validation and immutable human confirmation; persist/refresh/permission checks.
4. Multi-stage editorial checks and chief/editor assignments, deterministic role work queues and proposal review screens.
5. In-app reviewer lifecycle, round-bound anonymous report visibility, author revision and responsible-person decision.
6. Production/proof/local preview, complete real conversation/tool integration, all-role E2E and final security/review/fix.

## Completion evidence

- Source-grounded research and field dictionary covering submitted metadata, author snapshots, file revision/content addressing, access/assignment, stages/tasks, checks, rounds/invitations/reports, revisions/decisions, production/proofs/publication metadata.
- PostgreSQL migrations and DB constraints, existing-data compatibility, no invented legacy confirmations, role/object/anonymity checks, stale/duplicate/concurrent confirmation regression.
- One documented command starts the entire local product. All roles can log in and operate the actual sample end-to-end in Playwright, with refresh persistence and negative permission cases.
- Real model integration retains existing explicit opt-in and environment credential safety; deterministic business tests do not consume supplier API. Actual model tools tested on synthetic data when available, no claims about unexecuted provider behavior.
- scripts/verify.sh passes against isolated test stack without changing user's running live-model credentials. Additional migration/backup/recovery checks meaningful to this change also pass.
- README/PRODUCT/ARCHITECTURE/SECURITY/ROADMAP/DECISIONS/PROGRESS match actual implementation; report open limitations rather than hide them.

Do not mark Goal complete until all milestones/acceptance pass. Continue Research→Plan→Implement→Test→Review→Fix. Pause only at user's explicit request. Necessary external credentials/irreversible operations may require user help; optional implementation details do not.

Official Goal behavior: https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex and https://learn.chatgpt.com/docs/long-running-work . It is thread-scoped persistence, does not expand sandbox permissions and is not a daemon/global configuration change.

## Checkpoint evidence (2026-11-02, Goal remains active)

Research library and A/B real normalized intake implemented. Isolated scripts/verify.sh exit0:508 backend tests and24 Chromium E2E, including author conversation→actual files→independent confirmation→editor task; immutable/permissions/history/replay/concurrent-confirmation checks. Foundation migration24 rollback-only rehearsal checks; CheckRun component48 tests. Main live server/database unchanged. C gateway/UI, review/revision/decision/production/local preview and new-domain live acceptance are outstanding.

C checkpoint: all screening gates and returned-version recheck implemented. Isolated final verify exit0:532 backend tests,24 browser (same manuscript author→editor→chief→editor chain), static/migration/build/start passed. No live provider call/new main migration. D review invitation/report, E decision/revision, production/proof/preview and live normalized-domain safety acceptance remain pending. Goal stays active.

D checkpoint (2026-11-03): actual full verify exit0,612 backend+24 browser including same manuscript invitation/acceptance/anonymous download/report draft+human submit/editor finish. New-domain real DeepSeek, E decision/revision and F production/proof/local preview outstanding. Main service credentials/DB preserved; Goal remains active.
