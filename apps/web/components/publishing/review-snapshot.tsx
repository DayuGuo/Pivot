"use client";

import type { Proposal } from "./types";
import { dateText } from "./types";
import { invitationStatusLabels, ReviewFormQuestions, ReviewReportContent } from "./review-work";
import styles from "./publishing.module.css";

export function peerReviewConfirmationLabel(proposal: Proposal): string | null {
  switch (proposal.action_type) {
    case "open_review": return "确认并发出站内审稿邀请";
    case "invite_reviewers": return "确认并追加站内审稿邀请";
    case "respond_review_invitation": return proposal.payload.response?.outcome === "accept" ? "确认接受审稿邀请" : "确认拒绝本次审稿邀请";
    case "submit_review": return "确认提交审稿报告";
    case "finish_review": return "确认结束本轮评审";
    case "cancel_review_invitation": return "确认取消本次审稿邀请";
    default: return null;
  }
}

export function peerReviewAcknowledgment(proposal: Proposal): string | null {
  if (["open_review", "invite_reviewers"].includes(proposal.action_type)) return "我已核对本轮材料、审稿人名单、邀请正文和期限，并以负责人身份确认";
  if (proposal.action_type === "respond_review_invitation") return "我已核对本次邀请、本人回应和利益冲突声明，并以本人身份确认";
  if (proposal.action_type === "submit_review") return "我已核对本人的完整报告、推荐意见和本轮材料，并确认提交";
  if (["finish_review", "cancel_review_invitation"].includes(proposal.action_type)) return "我已核对本轮报告和全部待取消邀请、草稿任务，并以负责人身份确认";
  return null;
}

export function PeerReviewSnapshot({ proposal }: { proposal: Proposal }) {
  const payload = proposal.payload;
  if (["open_review", "invite_reviewers"].includes(proposal.action_type) && payload.review) {
    const review = payload.review;
    return <section className={styles.snapshot} aria-label="站内审稿邀请审核"><h2>第 {review.round_no} 轮 · {proposal.action_type === "open_review" ? "打开轮次与站内邀请" : "追加站内邀请"}</h2><p>本轮目标：{review.required_reports} 份提交报告。确认只创建站内邀请，不发送邮件。</p><h3>固定匿名材料</h3><ul className={styles.files}>{review.files.map(file => <li key={file.version_file_id}><strong>{file.display_name}</strong><span>用途：{file.role === "blinded_manuscript" ? "匿名稿件" : file.role}</span><code>SHA-256 {file.sha256}</code></li>)}</ul><p className={styles.hash}>材料集 SHA-256：<code>{review.material_digest}</code></p><h3>本次邀请</h3><ul className={styles.files}>{review.invitations.map(invitation => <li key={invitation.id}><strong>{invitation.reviewer_name ?? "审稿人"}{invitation.reviewer_email ? ` · ${invitation.reviewer_email}` : ""}</strong><span>第 {invitation.attempt_no} 次邀请</span><div className={styles.snapshot}><dl><dt>匿名稿件标题</dt><dd>{invitation.invitation_snapshot.title}</dd><dt>匿名摘要</dt><dd className={styles.preserve}>{invitation.invitation_snapshot.abstract}</dd><dt>站内邀请说明</dt><dd className={styles.preserve}>{invitation.invitation_snapshot.instructions}</dd><dt>回应截止</dt><dd>{dateText(invitation.response_due_at)}</dd><dt>报告截止</dt><dd>{dateText(invitation.report_due_at)}</dd></dl></div><code>邀请 SHA-256 {invitation.content_digest}</code></li>)}</ul><ReviewFormQuestions form={review.form_snapshot} /><p className={styles.hash}>表单 SHA-256：<code>{review.form_digest}</code></p></section>;
  }
  if (proposal.action_type === "respond_review_invitation" && payload.response) {
    const response = payload.response;
    return <section className={styles.snapshot} aria-label="本人审稿邀请回应审核"><h2>{response.outcome === "accept" ? "接受本次审稿邀请" : "拒绝本次审稿邀请"}</h2><p className={styles.notice}>{response.outcome === "accept" ? "确认接受后才开放本轮授权的匿名材料与报告草稿。" : "拒绝本次邀请不等于稿件拒稿，也不会提交审稿报告。"}</p>{payload.invitation && <dl><dt>匿名稿件标题</dt><dd>{payload.invitation.title}</dd><dt>匿名摘要</dt><dd className={styles.preserve}>{payload.invitation.abstract}</dd><dt>站内邀请说明</dt><dd className={styles.preserve}>{payload.invitation.instructions}</dd>{"response_due_at" in payload.invitation && <><dt>回应截止</dt><dd>{dateText(payload.invitation.response_due_at)}</dd><dt>报告截止</dt><dd>{dateText(payload.invitation.report_due_at)}</dd><dt>邀请尝试</dt><dd>第 {payload.invitation.attempt_no} 次</dd></>}</dl>}<dl><dt>本人回应</dt><dd>{response.outcome === "accept" ? "接受审稿邀请" : "拒绝本次邀请"}</dd><dt>本人利益冲突声明</dt><dd>{response.conflict_status === "none" ? "本人声明不存在利益冲突" : "本人声明存在利益冲突"}</dd><dt>回应说明</dt><dd className={styles.preserve}>{response.notes || "未填写"}</dd></dl></section>;
  }
  if (proposal.action_type === "submit_review" && payload.review_report) {
    const report = payload.review_report;
    return <section aria-label="本人审稿报告提交审核"><h2>本人审稿报告</h2><p className={styles.notice}>本次提交保存你的审稿意见与推荐建议，不会作出稿件录用、拒稿或公开发布决定。</p><ReviewReportContent report={report.data} form={payload.review?.form_snapshot} /><p className={styles.hash}>报告 SHA-256：<code>{report.content_digest}</code></p><p className={styles.hash}>表单 SHA-256：<code>{report.form_digest}</code></p>{payload.review && <><h3>本报告固定的匿名材料</h3><ul className={styles.files}>{payload.review.files.map(file => <li key={file.version_file_id}><strong>{file.display_name}</strong><code>SHA-256 {file.sha256}</code></li>)}</ul></>}</section>;
  }
  if (["finish_review", "cancel_review_invitation"].includes(proposal.action_type) && payload.review_closure) {
    const closure = payload.review_closure;
    return <section className={styles.snapshot} aria-label="评审结束与取消审核"><h2>{proposal.action_type === "finish_review" ? "结束本轮评审" : "取消本次审稿邀请"}</h2><dl><dt>原因</dt><dd className={styles.preserve}>{closure.reason}</dd><dt>已有提交报告</dt><dd>{closure.submitted_report_ids.length} 份，保留原始提交事实。</dd><dt>将取消的未完成邀请</dt><dd>{closure.cancel_invitation_ids.length} 项</dd></dl>{payload.cancellations?.length ? <ul className={styles.files}>{payload.cancellations.map(invitation => <li key={invitation.id}><strong>{invitation.reviewer_name ?? "审稿人"}{invitation.reviewer_email ? ` · ${invitation.reviewer_email}` : ""}</strong><span>{invitationStatusLabels[invitation.status] ?? invitation.status}</span>{(invitation.report_status || invitation.draft_state) && <span>报告状态：{invitation.report_status === "draft" || invitation.draft_state === "draft" ? "未提交草稿" : invitation.report_status ?? invitation.draft_state}</span>}</li>)}</ul> : closure.cancel_invitation_ids.length > 0 && <p className={styles.notice}>请在完整证据中核对将取消的邀请标识。</p>}<p className={styles.subtle}>取消会撤销对应待办与材料访问，不会把未完成报告伪记为已提交。结束评审后进入编辑建议阶段，不作出最终决定。</p></section>;
  }
  return null;
}
