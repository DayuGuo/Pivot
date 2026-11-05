"use client";
import { warnBeforeUnload } from "../browser";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Detail, OwnReviewReport, ReviewForm, ReviewMaterial, ReviewReportData, ReviewerWork, StaffReviewWork } from "./types";
import { dateText } from "./types";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

export const recommendationLabels = { unanswered: "尚未选择", accept: "建议录用", minor_revision: "建议小修", major_revision: "建议大修", reject: "建议拒稿" };
export const invitationStatusLabels: Record<string, string> = { pending: "等待回应", accepted: "已接受审稿", declined: "已拒绝本次邀请", cancelled: "已取消", expired: "已过期", submitted: "已提交报告" };
const allowed = (detail: Detail, action: string) => detail.allowed_actions.find(item => item.action === action);

function useDraftGuard(dirty: boolean, enabled = true) {
  const { setUnsaved } = usePublishing();
  useEffect(() => { if (!enabled) return; setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, enabled, setUnsaved]);
  useEffect(() => { if (!dirty) return; const warn = warnBeforeUnload; window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
}

function useReviewProposal(detail: Detail) {
  const { mutate, refresh } = usePublishing();
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [reviewURL, setReviewURL] = useState<string | null>(null); const [preparedRevision, setPreparedRevision] = useState<number | null>(null);
  function fail(message: string) { setError(message); }
  async function prepare(action: string, data: object) {
    if (!allowed(detail, action)) { fail("当前账号已无权执行此操作，请重新载入。"); return false; }
    setBusy(true); setError(""); setReviewURL(null);
    try {
      const result = await mutate<{ proposal_id: string }>(`/manuscripts/${detail.id}/proposals`, { expected_revision: detail.revision, action_type: action, data });
      setReviewURL(`/publishing/review/${result.proposal_id}`); setPreparedRevision(detail.revision); return true;
    } catch (failure) { fail((failure as Error).message); if (failure instanceof APIError && failure.status === 409) await refresh(); return false; }
    finally { setBusy(false); }
  }
  return { busy, error, fail, prepare, clear: () => setReviewURL(null), reviewURL: preparedRevision === detail.revision ? reviewURL : null };
}

function ProposalFeedback({ state }: { state: ReturnType<typeof useReviewProposal> }) {
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (state.error) errorRef.current?.focus(); }, [state.error]);
  return <>{state.error && <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>{state.error}</div>}{state.reviewURL && <p role="status"><Link className={styles.actionLink} href={state.reviewURL}>打开完整资料并由负责人确认</Link></p>}</>;
}

export function ReviewMaterials({ materials }: { materials: ReviewMaterial[] }) {
  return materials.length ? <ul className={styles.files}>{materials.map(file => <li key={file.round_file_id}><strong>固定轮次匿名材料</strong>{/^\/api\/publishing\/review-materials\/[0-9a-f-]{36}$/.test(file.download_url) ? <a href={file.download_url} download>{file.name}</a> : <span>{file.name}</span>}<small>{new Intl.NumberFormat("zh-CN").format(file.byte_size)} 字节 · {file.media_type}</small><code>SHA-256 {file.sha256}</code></li>)}</ul> : <p className={styles.subtle}>当前没有向你开放的轮次文件。</p>;
}

export function ReviewFormQuestions({ form }: { form: ReviewForm }) {
  return <section className={styles.section}><h2>本轮固定审稿表单</h2><p className={styles.subtle}>{form.key} · 第 {form.version} 版</p><ul className={styles.missing}>{form.questions.map(question => <li key={question.key}>{question.label}{question.required ? "（必填）" : ""} · {question.audience === "editor_only" ? "仅编辑可见" : "供后续作者反馈审核使用"}</li>)}</ul></section>;
}

export function StaffPeerReview({ detail, review }: { detail: Detail; review: StaffReviewWork }) {
  const proposal = useReviewProposal(detail); const [dirty, setDirty] = useState(false);
  const [reviewerIds, setReviewerIds] = useState<string[]>([]); const [requiredReports, setRequiredReports] = useState("");
  const [instructions, setInstructions] = useState(""); const [responseDays, setResponseDays] = useState("7"); const [reportDays, setReportDays] = useState("21");
  const [closureReason, setClosureReason] = useState(""); const [cancelPending, setCancelPending] = useState(false);
  const [cancelId, setCancelId] = useState(""); const [cancelReason, setCancelReason] = useState("");
  useDraftGuard(dirty);
  const invitationAction = allowed(detail, "open_review") ?? allowed(detail, "invite_reviewers");
  const unfinished = review.invitations.filter(invitation => ["pending", "accepted"].includes(invitation.status));
  const activeReviewers = new Set(review.invitations.filter(invitation => ["pending", "accepted", "submitted"].includes(invitation.status)).map(invitation => invitation.reviewer_id));
  function edited() { setDirty(true); proposal.clear(); }
  async function invite() {
    if (!invitationAction) return;
    const target = Number(requiredReports); const response = Number(responseDays); const report = Number(reportDays);
    if (reviewerIds.length < 1 || reviewerIds.length > 3) { proposal.fail("请选择 1 至 3 位真实审稿人。"); return; }
    if (instructions.trim().length < 10) { proposal.fail("请填写至少10个字符的站内审稿邀请说明。"); return; }
    if (!Number.isInteger(response) || response < 1 || response > 30 || !Number.isInteger(report) || report < 2 || report > 90 || report <= response) { proposal.fail("回应期限为 1 至 30 天；报告期限必须晚于回应期限，并且不超过 90 天。"); return; }
    if (invitationAction.action === "open_review" && (!Number.isInteger(target) || target < 1 || target > 3)) { proposal.fail("请明确选择本轮所需的报告份数。"); return; }
    const data = { reviewer_ids: reviewerIds, instructions: instructions.trim(), response_due_days: response, report_due_days: report, ...(invitationAction.action === "open_review" ? { required_reports: target } : {}) };
    if (await proposal.prepare(invitationAction.action, data)) setDirty(false);
  }
  async function finish() {
    if (!closureReason.trim()) { proposal.fail("请说明结束本轮评审的原因。"); return; }
    if (unfinished.length && !cancelPending) { proposal.fail("仍有未完成邀请，请明确确认取消其待办后再准备结束。"); return; }
    if (await proposal.prepare("finish_review", { reason: closureReason.trim(), cancel_pending: cancelPending })) setDirty(false);
  }
  async function cancel() {
    if (!cancelId || !cancelReason.trim()) { proposal.fail("请选择要取消的未完成邀请，并填写原因。"); return; }
    if (await proposal.prepare("cancel_review_invitation", { invitation_id: cancelId, reason: cancelReason.trim() })) setDirty(false);
  }
  return <section aria-label="站内同行评审" className={styles.section}><h2>{review.round ? `第 ${review.round.round_no} 轮同行评审` : "准备同行评审"}</h2>
    {review.round && <div className={styles.notice}><p>已提交报告 {review.round.submitted_reports} / {review.round.required_reports} · 已接受 {review.round.accepted_count} · 待回应 {review.round.pending_count}</p><p>轮次状态：{review.round.status === "open" ? "进行中" : review.round.status === "closed" ? "已结束" : review.round.status}</p></div>}
    <ProposalFeedback state={proposal} />
    {invitationAction && <form onSubmit={event => { event.preventDefault(); void invite(); }}><fieldset className={styles.fields} disabled={proposal.busy}><legend>{invitationAction.action === "open_review" ? "打开轮次并准备站内邀请" : "追加站内审稿邀请"}</legend><p className={styles.subtle}>只向现有期刊成员创建站内邀请，不发送邮件。</p><div>{review.eligible_reviewers.length ? review.eligible_reviewers.map(reviewer => <label className={styles.checkbox} key={reviewer.id}><input type="checkbox" name="reviewer_ids" value={reviewer.id} disabled={activeReviewers.has(reviewer.id) || (!reviewerIds.includes(reviewer.id) && reviewerIds.length >= 3)} checked={reviewerIds.includes(reviewer.id)} onChange={event => { setReviewerIds(previous => event.target.checked ? [...previous, reviewer.id] : previous.filter(id => id !== reviewer.id)); edited(); }} />{reviewer.name} · {reviewer.email}{activeReviewers.has(reviewer.id) ? "（本轮已有有效邀请）" : ""}</label>) : <p>暂无符合条件的审稿人成员。</p>}</div>
      {invitationAction.action === "open_review" && <div className={styles.fieldControl}><label htmlFor="review-required-reports">本轮所需报告份数</label><select id="review-required-reports" name="required_reports" value={requiredReports} onChange={event => { setRequiredReports(event.target.value); edited(); }}><option value="">请明确选择</option>{[1, 2, 3].map(count => <option key={count} value={count}>{count} 份</option>)}</select></div>}
      <div className={styles.fieldControl}><label htmlFor="review-instructions">站内邀请说明</label><textarea id="review-instructions" name="instructions" autoComplete="off" rows={4} maxLength={4000} value={instructions} onChange={event => { setInstructions(event.target.value); edited(); }} /></div><div className={styles.fieldRow}><label htmlFor="review-response-days">回应期限（天）<input id="review-response-days" name="response_due_days" type="number" min={1} max={30} value={responseDays} onChange={event => { setResponseDays(event.target.value); edited(); }} /></label><label htmlFor="review-report-days">报告期限（天）<input id="review-report-days" name="report_due_days" type="number" min={Math.max(2, Number(responseDays) + 1)} max={90} value={reportDays} onChange={event => { setReportDays(event.target.value); edited(); }} /></label></div><button type="submit">{proposal.busy ? "正在准备…" : invitationAction.label}</button>
    </fieldset></form>}
    <h2>邀请记录</h2>{review.invitations.length ? <ul className={styles.files}>{review.invitations.map(invitation => <li key={invitation.id}><strong>{invitation.reviewer_name} · {invitation.reviewer_email}</strong><span>{invitationStatusLabels[invitation.status] ?? invitation.status} · 第 {invitation.round_no} 轮 · 第 {invitation.attempt_no} 次邀请</span><small>回应截止 {dateText(invitation.response_due_at)} · 报告截止 {dateText(invitation.report_due_at)}</small>{invitation.conflict_status && <small>利益冲突：{invitation.conflict_status === "none" ? "本人声明无冲突" : invitation.conflict_status === "declared" ? "本人声明存在冲突" : "未声明"}</small>}{invitation.notes && <p className={styles.preserve}>{invitation.notes}</p>}</li>)}</ul> : <p className={styles.subtle}>尚未发出站内邀请。</p>}
    {allowed(detail, "cancel_review_invitation") && <form className={styles.fields} onSubmit={event => { event.preventDefault(); void cancel(); }}><div className={styles.fieldControl}><label htmlFor="review-cancel-invitation">要取消的邀请</label><select id="review-cancel-invitation" name="invitation_id" value={cancelId} disabled={proposal.busy} onChange={event => { setCancelId(event.target.value); edited(); }}><option value="">请选择未完成邀请</option>{unfinished.map(invitation => <option key={invitation.id} value={invitation.id}>{invitation.reviewer_name} · 第 {invitation.attempt_no} 次 · {invitationStatusLabels[invitation.status]}</option>)}</select></div><div className={styles.fieldControl}><label htmlFor="review-cancel-reason">取消原因</label><textarea id="review-cancel-reason" name="cancel_reason" autoComplete="off" rows={3} maxLength={4000} value={cancelReason} disabled={proposal.busy} onChange={event => { setCancelReason(event.target.value); edited(); }} /></div><button disabled={proposal.busy}>{allowed(detail, "cancel_review_invitation")?.label}</button></form>}
    <h2>本轮报告</h2>{review.reports.length ? review.reports.map(report => <details className={styles.section} key={report.id}><summary>{report.reviewer_name} · {report.status === "submitted" ? "已提交" : "草稿"} · 修订 {report.revision}</summary><ReviewReportContent report={report} form={review.form} /></details>) : <p className={styles.subtle}>尚无报告。</p>}
    {allowed(detail, "finish_review") && <form className={styles.fields} onSubmit={event => { event.preventDefault(); void finish(); }}><h3>结束本轮评审</h3><div className={styles.fieldControl}><label htmlFor="review-closure-reason">结束原因</label><textarea id="review-closure-reason" name="closure_reason" autoComplete="off" rows={3} maxLength={4000} value={closureReason} disabled={proposal.busy} onChange={event => { setClosureReason(event.target.value); edited(); }} /></div>{unfinished.length > 0 && <label className={styles.checkbox}><input name="cancel_pending" type="checkbox" checked={cancelPending} disabled={proposal.busy} onChange={event => { setCancelPending(event.target.checked); edited(); }} />我确认结束时取消以上 {unfinished.length} 项未完成邀请及待办</label>}<button disabled={proposal.busy}>{allowed(detail, "finish_review")?.label}</button></form>}
    <ReviewMaterials materials={review.materials} />{review.form && <ReviewFormQuestions form={review.form} />}
  </section>;
}

export function ReviewerPeerReview({ detail, review }: { detail: Detail; review: ReviewerWork }) {
  const proposal = useReviewProposal(detail); const [outcome, setOutcome] = useState<"" | "accept" | "decline">("");
  const [conflict, setConflict] = useState<"" | "none" | "declared">(""); const [notes, setNotes] = useState(""); const [dirty, setDirty] = useState(false);
  useDraftGuard(dirty, review.can_respond);
  async function respond() {
    if (!outcome || !conflict) { proposal.fail("请分别选择接受或拒绝本次邀请，以及本人的利益冲突声明。"); return; }
    if (outcome === "accept" && conflict !== "none") { proposal.fail("存在利益冲突时不能接受审稿，请选择拒绝本次邀请并说明情况。"); return; }
    if (await proposal.prepare("respond_review_invitation", { invitation_id: review.invitation.id, outcome, conflict_status: conflict, notes: notes.trim() })) setDirty(false);
  }
  function edited() { setDirty(true); proposal.clear(); }
  return <><header className={styles.recordHeader}><div><span>{detail.number}</span><span className={styles.status}>{detail.stage_label}</span></div><h1>{review.invitation.title}</h1><p>第 {review.round.round_no} 轮 · {invitationStatusLabels[review.invitation.status] ?? review.invitation.status}</p></header><section className={styles.panel}><div className={styles.snapshot}><dl><dt>匿名摘要</dt><dd className={styles.preserve}>{review.invitation.abstract}</dd><dt>站内邀请说明</dt><dd className={styles.preserve}>{review.invitation.instructions}</dd><dt>回应截止</dt><dd>{dateText(review.invitation.response_due_at)}</dd><dt>报告截止</dt><dd>{dateText(review.invitation.report_due_at)}</dd></dl></div>
    {review.can_respond && allowed(detail, "respond_review_invitation") && <form className={styles.section} onSubmit={event => { event.preventDefault(); void respond(); }}><fieldset className={styles.fields} disabled={proposal.busy}><legend>回应本次站内邀请</legend><div className={styles.fieldControl}><label htmlFor="review-invitation-outcome">本次邀请回应</label><select id="review-invitation-outcome" name="outcome" value={outcome} onChange={event => { setOutcome(event.target.value as typeof outcome); edited(); }}><option value="">请本人选择</option><option value="accept">接受审稿邀请</option><option value="decline">拒绝本次邀请</option></select></div><div className={styles.fieldControl}><label htmlFor="review-conflict-status">本人利益冲突声明</label><select id="review-conflict-status" name="conflict_status" value={conflict} onChange={event => { setConflict(event.target.value as typeof conflict); edited(); }}><option value="">请本人选择</option><option value="none">我声明不存在利益冲突</option><option value="declared">我声明存在利益冲突</option></select></div><div className={styles.fieldControl}><label htmlFor="review-response-notes">回应说明</label><textarea id="review-response-notes" name="response_notes" autoComplete="off" rows={3} maxLength={4000} value={notes} onChange={event => { setNotes(event.target.value); edited(); }} /></div><button>{proposal.busy ? "正在准备…" : allowed(detail, "respond_review_invitation")?.label}</button></fieldset></form>}
    <ProposalFeedback state={proposal} />
    {!review.can_respond && <p className={styles.notice}>本次邀请：{invitationStatusLabels[review.invitation.status] ?? review.invitation.status}；利益冲突：{review.invitation.conflict_status === "none" ? "本人已声明无冲突" : review.invitation.conflict_status === "declared" ? "本人已声明存在冲突" : "尚未声明"}{review.invitation.response_notes && <span className={styles.preserve}>。{review.invitation.response_notes}</span>}</p>}
    <h2>本轮匿名材料</h2><ReviewMaterials materials={review.materials} />
    {review.report && (review.can_edit_report && review.report.status === "draft" ? <ReviewReportEditor key={review.report.id} detail={detail} review={review} report={review.report} /> : <section className={styles.section}><h2>本人审稿报告</h2><ReviewReportContent report={review.report} form={review.form} /></section>)}
    <ReviewFormQuestions form={review.form} />
  </section></>;
}

export function ReviewReportContent({ report, form }: { report: ReviewReportData & { status?: string; submitted_at?: string | null }; form?: ReviewForm | null }) {
  const questions = form?.questions ?? [{ key: "rigor" as const, label: "方法与证据是否充分", audience: "author" as const }, { key: "confidential_assessment" as const, label: "给编辑的保密评估", audience: "editor_only" as const }];
  return <div className={styles.snapshot}><dl><dt>给作者的评审意见</dt><dd className={styles.preserve}>{report.author_text || "尚未填写"}</dd><dt>仅给编辑的保密意见</dt><dd className={styles.preserve}>{report.editor_private_text || "尚未填写"}</dd>{questions.map(question => <div key={question.key}><dt>{question.label} · {question.audience === "editor_only" ? "仅编辑可见" : "供后续作者反馈审核使用"}</dt><dd className={styles.preserve}>{report.answers_json[question.key] || "尚未填写"}</dd></div>)}<dt>审稿人推荐意见</dt><dd>{recommendationLabels[report.recommendation]}（建议，不是编辑或主编的最终决定）</dd>{report.submitted_at && <><dt>本人提交时间</dt><dd>{dateText(report.submitted_at)}</dd></>}</dl></div>;
}

function ReviewReportEditor({ detail, review, report }: { detail: Detail; review: ReviewerWork; report: OwnReviewReport }) {
  const { mutate, refresh } = usePublishing(); const proposal = useReviewProposal(detail);
  const [data, setData] = useState<ReviewReportData>(() => ({ author_text: report.author_text, editor_private_text: report.editor_private_text, answers_json: { ...report.answers_json }, recommendation: report.recommendation }));
  const [baseRevision, setBaseRevision] = useState(report.revision); const [dirty, setDirty] = useState(false); const [busy, setBusy] = useState(false); const [conflict, setConflict] = useState(false); const [notice, setNotice] = useState("");
  useDraftGuard(dirty);
  if (!dirty && !busy && report.revision > baseRevision) { setBaseRevision(report.revision); setData({ author_text: report.author_text, editor_private_text: report.editor_private_text, answers_json: { ...report.answers_json }, recommendation: report.recommendation }); }
  const stale = report.revision !== baseRevision || conflict;
  const candidates = review.report_candidates;
  const canAdopt = !!candidates && ((!data.author_text.trim() && !!candidates.author_text?.trim()) || (!data.editor_private_text.trim() && !!candidates.editor_private_text?.trim()) || (!data.answers_json.rigor?.trim() && !!candidates.answers_json?.rigor?.trim()) || (!data.answers_json.confidential_assessment?.trim() && !!candidates.answers_json?.confidential_assessment?.trim()));
  function edited() { setDirty(true); setNotice(""); proposal.clear(); }
  function adopt() {
    if (!candidates) return;
    setData(previous => ({ ...previous, author_text: previous.author_text.trim() ? previous.author_text : candidates.author_text ?? previous.author_text, editor_private_text: previous.editor_private_text.trim() ? previous.editor_private_text : candidates.editor_private_text ?? previous.editor_private_text, answers_json: { rigor: previous.answers_json.rigor?.trim() ? previous.answers_json.rigor : candidates.answers_json?.rigor ?? previous.answers_json.rigor ?? "", confidential_assessment: previous.answers_json.confidential_assessment?.trim() ? previous.answers_json.confidential_assessment : candidates.answers_json?.confidential_assessment ?? previous.answers_json.confidential_assessment ?? "" } })); edited();
  }
  async function save() {
    setBusy(true); setNotice("");
    try { const result = await mutate<{ revision: number }>(`/review-reports/${report.id}`, { expected_revision: baseRevision, data }, "PATCH"); setBaseRevision(result.revision); setDirty(false); setConflict(false); setNotice("审稿报告草稿已保存，尚未提交。"); await refresh(); }
    catch (failure) { proposal.fail((failure as Error).message); if (failure instanceof APIError && failure.status === 409) setConflict(true); }
    finally { setBusy(false); }
  }
  async function reload() {
    if (dirty && !window.confirm("放弃当前未保存的审稿报告修改，并载入已保存内容？")) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/publishing/manuscripts/${detail.id}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new APIError(response.status, "无法载入已保存报告，当前输入仍保留。请检查连接后重试。");
      const latest: Detail = await response.json();
      if (latest.review?.mode !== "reviewer" || latest.review.report?.id !== report.id) throw new Error("报告访问权限或目标已变化，请刷新工作区。");
      const saved = latest.review.report;
      setBaseRevision(saved.revision); setData({ author_text: saved.author_text, editor_private_text: saved.editor_private_text, answers_json: { ...saved.answers_json }, recommendation: saved.recommendation }); setDirty(false); setConflict(false); await refresh();
    } catch (failure) { proposal.fail((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <section className={styles.section} aria-label="本人审稿报告编辑"><h2>本人审稿报告</h2><p className={styles.subtle}>推荐意见仅供编辑参考，不会直接录用或拒绝稿件。草稿不计为已提交报告。</p>
    {stale && <div className={styles.notice} role="alert">报告已更新。当前输入仍保留，请复制需要的内容后重新载入。<button onClick={() => void reload()} disabled={busy}>重新载入已保存报告</button></div>}
    {candidates && <section className={styles.notice} aria-label="AI 审稿报告候选"><h3>AI 审稿报告候选 · 未核实</h3>{candidates.author_text && <p className={styles.preserve}>给作者的意见候选：{candidates.author_text}</p>}{candidates.editor_private_text && <p className={styles.preserve}>保密意见候选：{candidates.editor_private_text}</p>}{candidates.answers_json?.rigor && <p className={styles.preserve}>方法与证据候选：{candidates.answers_json.rigor}</p>}{candidates.answers_json?.confidential_assessment && <p className={styles.preserve}>保密评估候选：{candidates.answers_json.confidential_assessment}</p>}<p>只填入空白文字，不覆盖人工内容；推荐意见、利益冲突和提交仍由本人决定。</p><button onClick={adopt} disabled={!canAdopt || busy || proposal.busy}>采用空白字段的审稿候选</button></section>}
    <ProposalFeedback state={proposal} /><p className={styles.saved} aria-live="polite">{notice || (dirty ? "有未保存的报告修改" : "")}</p>
    <form onSubmit={event => { event.preventDefault(); void save(); }} noValidate><fieldset className={styles.fields} disabled={busy || proposal.busy}><div className={styles.fieldControl}><label htmlFor="review-author-text">给作者的评审意见</label><textarea id="review-author-text" name="author_text" autoComplete="off" rows={7} maxLength={12000} value={data.author_text} onChange={event => { setData(previous => ({ ...previous, author_text: event.target.value })); edited(); }} /></div><div className={styles.fieldControl}><label htmlFor="review-editor-private">仅给编辑的保密意见</label><textarea id="review-editor-private" name="editor_private_text" autoComplete="off" rows={4} maxLength={4000} value={data.editor_private_text} onChange={event => { setData(previous => ({ ...previous, editor_private_text: event.target.value })); edited(); }} /></div>{review.form.questions.map(question => <div className={styles.fieldControl} key={question.key}><label htmlFor={`review-answer-${question.key}`}>{question.label}</label><textarea id={`review-answer-${question.key}`} name={`answers_json.${question.key}`} autoComplete="off" rows={4} maxLength={4000} value={data.answers_json[question.key] ?? ""} onChange={event => { setData(previous => ({ ...previous, answers_json: { ...previous.answers_json, [question.key]: event.target.value } })); edited(); }} /><p className={styles.subtle}>{question.required ? "必填。" : ""}{question.audience === "editor_only" ? "仅编辑可见。" : "供后续作者反馈审核使用。"}</p></div>)}<div className={styles.fieldControl}><label htmlFor="review-recommendation">审稿人推荐意见</label><select id="review-recommendation" name="recommendation" value={data.recommendation} onChange={event => { setData(previous => ({ ...previous, recommendation: event.target.value as ReviewReportData["recommendation"] })); edited(); }}>{Object.entries(recommendationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><button disabled={stale}>{busy ? "正在保存…" : "保存审稿报告草稿"}</button></fieldset></form>
    {allowed(detail, "submit_review") && <button disabled={dirty || stale || busy || proposal.busy} onClick={() => void proposal.prepare("submit_review", { report_id: report.id, expected_report_revision: report.revision })}>{proposal.busy ? "正在准备…" : allowed(detail, "submit_review")?.label}</button>}
    {dirty && <p className={styles.subtle}>请先保存报告草稿，再打开独立提交审核。</p>}
  </section>;
}
