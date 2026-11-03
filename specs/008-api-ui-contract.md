# D in-app review UI/API integration contract

Planned implementation after C. Keep same always-mounted primary chat and /publishing/review/:proposalId final confirmation. No mail, external tokens or final chief decisions. Only render controls returned in allowed_actions; API checks actual role/journal/typed target/assignment/COI.

## Detail extension

Detail.review is null outside review slice, otherwise one role-specific DTO:

- Staff: `{mode:'staff', round:null|RoundSummary, eligible_reviewers:[{id,name,email}], invitations:StaffInvitation[], reports:StaffReport[], materials:Material[], form:ReviewForm|null}`. Actual Member reviewer candidates only, no invented match scores. StaffInvitation={id,reviewer_id,reviewer_name,reviewer_email,status,attempt_no,response_due_at,report_due_at,round_no}; optional notes/conflict_status from actual response. StaffReport={id,reviewer_name,status,revision,author_text,editor_private_text,answers_json,recommendation,submitted_at}. No author sees this DTO.
- Reviewer: `{mode:'reviewer', round:RoundSummary, invitation:OwnInvitation, report:null|OwnReport, materials:Material[], form:ReviewForm, can_respond:boolean, can_edit_report:boolean}`. OwnInvitation={id,status,attempt_no,title,abstract,instructions,response_due_at,report_due_at,conflict_status,response_notes}. No other reviewers or author identities/metadata. Pending materials=[], report=null; accepting is explicit human confirmation, not merely clicking prepare. OwnReport={id,status,revision,author_text,editor_private_text,answers_json,recommendation,submitted_at}. Only own report, even after round closes; no new file grant. Generic author Snapshot must not render here; show anonymous title/abstract/form/materials and own response/report.
- Author: null or `{mode:'author'}` with no unreleased reports/IDs/reviewers/private fields. Existing actual stage is enough.

RoundSummary={id,round_no,version_id,status,required_reports,submitted_reports,accepted_count,pending_count}. Material={id:VersionFileID,round_file_id,name:serverAnonymousName,sha256,byte_size,media_type,download_url:'/api/publishing/review-materials/<RoundFileID>'}; server authorizes even direct guesses. Do not show original filenames. Round/file/form never follows current manuscript changes.

ReviewForm={key:'basic_peer_review',version:1,questions:[{key:'rigor',label:'方法与证据是否充分',kind:'text',required:true,audience:'author'},{key:'confidential_assessment',label:'给编辑的保密评估',kind:'text',required:true,audience:'editor_only'}]}. Backend typed schema requires author_text>=40 chars, rigor>=10, confidential_assessment>=10, editor_private_text optional<=4000; recommendation accept|minor_revision|major_revision|reject, unanswered allowed in draft only. Clarify reviewer recommendation is a suggestion, never final acceptance/rejection.

## Mutations

Same POST /manuscripts/{id}/proposals {request_id,expected_revision,action_type,data} then existing independent full review/confirmation endpoint. Preparation never mutates invitation acceptance/report submission/final manuscript result.

- open_review: data `{reviewer_ids:string[] (1..3),required_reports:1..3,instructions:string,response_due_days:1..30,report_due_days:1..90}`. ReviewerIds multiselect actual candidates, target count explicit, instructions required. Shows full fixed anonymous materials/form/invitations/deadlines in independent snapshot before editor confirms. Creates first round + in-app invites, no emails. Only reviewer_selection with no open round.
- invite_reviewers: data `{reviewer_ids:string[],instructions:string,response_due_days:number,report_due_days:number}`. Same fixed current round/target/form/materials; terminal decline permits new attempt. No target edit. Available while round open; no active duplicate reviewer.
- respond_review_invitation: data `{invitation_id:string,outcome:'accept'|'decline',conflict_status:'none'|'declared',notes:string}`. Defaults unselected. Acceptance requires explicit no conflict and backend known COI check; decline is not manuscript rejection. Independent snapshot only own anonymous invitation summary/response, no full author version.
- finish_review: data `{reason:string,cancel_pending:boolean}`. Available only required submitted reports met. If any pending/accepted unfinished invite exists, explicit cancel_pending=true required; independent snapshot lists exact affected invites/tasks/reason before confirmation. Closes round, cancels pending work/revokes grants without fake report submission; next is editor_recommendation, no final decision.
- submit_review: data `{report_id:string,expected_report_revision:number}`. Backend snapshots saved own report/form/fixed materials/recommendation, requires complete typed answers, then human confirms. This is reviewer report submission, not editor/chief decision.
- cancel_review_invitation: data `{invitation_id,reason}` if backend exposes action. Explicit per-invitation cancellation snapshot; preserve attempt/history.

PATCH /review-reports/{reportId} `{request_id,expected_revision:report.revision,data:{author_text,editor_private_text,answers_json:{rigor:string,confidential_assessment:string},recommendation:'unanswered'|'accept'|'minor_revision'|'major_revision'|'reject'}}` -> `{report_id,revision,manuscript_revision}`. Save draft incomplete allowed, creates no confirmation/submitted count. Both report revision and manuscript revision increment, old preparations expire; UI retains local edits on409 and offers reload. Save draft then prepare submit, never auto submit. Store only own real data, no fixture defaults.

## Independent review payload DTOs

Proposal.payload.version may be null for reviewer operations to avoid any generic full-author snapshot. Additional typed fields:

- `review`: round_id,round_no,version_id,required_reports,form_snapshot,form_digest,material_digest,files[{version_file_id,sha256,role,display_name}],invitations[{id,reviewer_id,reviewer_name,reviewer_email,attempt_no,invitation_snapshot:{title,abstract,instructions},response_due_at,report_due_at,content_digest}]. Editor owns snapshot, identities allowed there; reviewer sees only own anonymous invitation when responding.
- `response`: invitation_id,outcome,conflict_status,notes plus `invitation` anonymous own summary (separate from staff review list). Must show acceptance/decline and COI explicitly.
- `review_report`: id,invitation_id,form_digest,data:{author_text,editor_private_text,answers_json,recommendation},content_digest. Reviewer sees all own sections and actual form meaning, recommendation labelled suggestion.
- `review_closure`: round_id,reason,submitted_report_ids,cancel_invitation_ids plus `cancellations` readable own staff list (reviewer name/status/draft state). Chief final decision absent.

Use Chinese exact human confirmation labels: open_review='确认并发出站内审稿邀请'; invite_reviewers='确认并追加站内审稿邀请'; respond accept='确认接受审稿邀请', decline='确认拒绝本次审稿邀请'; submit_review='确认提交审稿报告'; finish_review='确认结束本轮评审'; cancel='确认取消本次审稿邀请'. All default acknowledgment false and current responsible identity; chat visible. No generic raw JSON as only way to review these contents. Model can explain/prepare safe candidates but cannot final confirm.

## Browser acceptance

Extend same real author→editor→chief→quality chain: staff opens fixed round/invite, reviewer pending sees only anonymous summary/no files, explicitly accepts/noCOI, now reads file and fills actual report, saves and independently confirms, editor sees submitted report and closes via explicit confirmation. Author never sees report IDs/private comments/identity. Decline/re-invite and expired/revoked/version failures separately tested. All refresh/role/mount/viewport behavior stays. Next editor recommendation/chief decision/revision belong E, not fabricated D completion.
