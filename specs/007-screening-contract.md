# v0.1 C: responsible-person screening gates

Status: implementation contract, not acceptance evidence. Root integrates; checks.py/09b migration are isolated reviewed components. Read both OJS stage-assignment/decision source and Janeway SubmissionCheck/WorkflowLog/EditorAssignment before changes. See comparison/database-decisions DB02/04/05/06. Do not treat an upstream UI “status” as permission to bypass confirmation.

## Deterministic sequence

precheck_completeness → similarity_review → technical_screening → chief_scope → assign_editor → editor_quality → reviewer_selection. The three first gates belong to the explicitly assigned precheck editor. Chief scope and assignment belong to assigned chief; quality to the newly assigned handling editor. A role is necessary but never grants a case by itself. Owner and known version coauthors cannot approve; email matching can prevent a conflict but never grant access.

Each gate prepares a version/revision/policy/task-bound immutable ActionProposal. CheckRun becomes finalized only within the responsible person's independent confirmation transaction, with matching proposal/confirmation/task/version/actor. Notes, explicit manual review declarations, outcome and return reason are in its full snapshot. Preparing or chatting cannot complete a gate. Return creates a new author version and preserves frozen originals, completed steps and evidence; resubmission restarts completeness precheck for the new version; the original failed gate remains in return provenance. Older checks cannot certify a changed version.

Similarity uses an actual uploaded UTF8 report plus explicit `manual_review`. Store the report as FileObject and staff-owned schema-specific FormDraft binding for this manuscript/version; finalized CheckRun references it, never append VersionFile to a frozen version. Verify actual report bytes at prepare and confirm. Report download requires the assigned staff/case permission; the author does not receive staff-only report evidence merely because they own the manuscript. Upload/replacement changes the workflow revision and expires prepared snapshots.

Assign-editor proposal binds selected eligible local user ID/name and current membership role, then rechecks at confirmation. Assignment/Manuscript.editor_id projection/new work item/audit/receipt commit atomically. No emails or real invitations. Complete quality advances to reviewer_selection; downstream review is a separate increment.

## UI and model boundary

Central conversation remains mounted. Right-hand actual task form exposes outcome/notes/reason and the required review checkboxes; chief assignment exposes only eligible actual editors. Full independent review prominently renders the proposed finding/report hash/editor, with explicit confirmation. No fake next-gate controls.

The model can read state/material and suggest notes or explain missing evidence. Manual declarations and final confirmations belong to humans. Do not expose a generic prepare-review tool that falsely checks material/report/scope declarations on behalf of a user. The next tool contract can stage unverified check candidates; responsible forms explicitly adopt them.

## Required verification

Actual PostgreSQL full success sequence and returned-version resubmission, never preseeded final stages. Wrong/changed actor, owner/coauthor, other journal/object, no report, bad CAS, stale/reassigned proposal, duplicate UUID, task/history consistency and atomic rollback. Browser staff precheck/report/technical, chief assignment and editor quality through the independent review route; refresh persists. Existing A/B and legacy regression stays. Database check constraints tested independently from DTO checks. Source-field/migration-test mapping updated only with actual evidence.
