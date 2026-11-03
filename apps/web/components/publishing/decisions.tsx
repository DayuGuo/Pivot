"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { AssessmentSnapshot, AuthorReportSnapshot, DecisionCode, DecisionSnapshot, Detail, EditorialProjection, Proposal, RecommendationSnapshot, RevisionKind } from "./types";
import { dateText } from "./types";
import { ReviewReportContent } from "./review-work";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

const decisionLabels: Record<DecisionCode, string> = { request_revision: "要求作者修回", accept: "录用", reject: "拒稿" };
const revisionLabels: Record<RevisionKind, string> = { minor: "小修", major: "大修" };
type StaffEditorial = Extract<EditorialProjection, { mode: "staff" }>;
const actionFor = (detail: Detail, action: string) => detail.allowed_actions.find(item => item.action === action);

export function AnonymousAuthorReport({ snapshot }: { snapshot: AuthorReportSnapshot }) {
  return <div className={styles.snapshot}><p className={styles.preserve}>{snapshot.author_text}</p><dl>{snapshot.questions.map(question => <div key={question.key}><dt>{question.label}</dt><dd className={styles.preserve}>{snapshot.answers[question.key] || "未提供"}</dd></div>)}</dl></div>;
}

export function EditorialFeedback({ detail }: { detail: Detail }) {
  const editorial = detail.editorial;
  if (!editorial || editorial.mode !== "author") return null;
  const request = editorial.revision_request;
  return <section className={styles.panel} aria-label="正式编辑反馈">{request && <div className={styles.notice}><h2>第 {request.request_no} 次正式修回 · {revisionLabels[request.kind]}</h2><p className={styles.preserve}>{request.author_instructions}</p><p>截止时间：{dateText(request.due_at)}</p><p>请修改当前准备版本、重新回答作者声明，并在稿件文件中上传“修回说明”；提交仍需本人独立审核确认。</p>{request.rereview_required && <p>本次修回需要重新同行评审。</p>}</div>}
    {editorial.feedback.map(feedback => <section className={styles.section} key={feedback.decision_id}><h2>{decisionLabels[feedback.decision_code]}{feedback.revision_kind ? ` · ${revisionLabels[feedback.revision_kind]}` : ""}</h2><p className={styles.subtle}>已确认于 {dateText(feedback.decided_at)}</p><p className={styles.preserve}>{feedback.author_letter}</p>{feedback.instructions && <p className={styles.preserve}>{feedback.instructions}</p>}{feedback.due_at && <p>修回截止：{dateText(feedback.due_at)}</p>}{feedback.reports.map(report => <section key={report.ordinal} className={styles.section}><h3>匿名评审意见 {report.ordinal}</h3><AnonymousAuthorReport snapshot={report.author_snapshot} /></section>)}</section>)}
  </section>;
}

export function EditorialActions({ detail, editorial }: { detail: Detail; editorial: StaffEditorial }) {
  const { mutate, refresh, setUnsaved } = usePublishing();
  const [code, setCode] = useState<"" | DecisionCode>(""); const [kind, setKind] = useState<"" | RevisionKind>("");
  const [rationale, setRationale] = useState(""); const [letter, setLetter] = useState("");
  const [instructions, setInstructions] = useState(""); const [dueDays, setDueDays] = useState("");
  const [shareIds, setShareIds] = useState<string[]>([]); const [shareReviewed, setShareReviewed] = useState(false);
  const [outcome, setOutcome] = useState<"" | "ready_for_chief" | "rereview">(""); const [notes, setNotes] = useState("");
  const [currentReviewed, setCurrentReviewed] = useState(false); const [responseReviewed, setResponseReviewed] = useState(false); const [anonymousReviewed, setAnonymousReviewed] = useState(false);
  const [dirty, setDirty] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [reviewURL, setReviewURL] = useState<string | null>(null); const [baseRevision, setBaseRevision] = useState(detail.revision);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
  useEffect(() => { if (!dirty) return; const warn = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  if (detail.revision !== baseRevision) { setBaseRevision(detail.revision); setShareReviewed(false); setCurrentReviewed(false); setResponseReviewed(false); setAnonymousReviewed(false); setReviewURL(null); }
  const recommendationAction = actionFor(detail, "recommend_decision"); const decisionAction = actionFor(detail, "record_decision"); const assessmentAction = actionFor(detail, "assess_revision");
  const decisionForm = recommendationAction ?? decisionAction;
  function edited() { setDirty(true); setReviewURL(null); }
  function fail(message: string) { setError(message); requestAnimationFrame(() => errorRef.current?.focus()); }
  async function prepare(action: string, data: object) {
    if (!actionFor(detail, action)) { fail("当前账号无权执行此操作，请重新载入。"); return; }
    setBusy(true); setError(""); setReviewURL(null);
    try { const result = await mutate<{ proposal_id: string }>(`/manuscripts/${detail.id}/proposals`, { expected_revision: detail.revision, action_type: action, data }); setReviewURL(`/publishing/review/${result.proposal_id}`); setDirty(false); setUnsaved(false); }
    catch (failure) { fail((failure as Error).message); if (failure instanceof APIError && failure.status === 409) await refresh(); }
    finally { setBusy(false); }
  }
  function prepareDecision() {
    if (!decisionForm) return;
    if (!code || (code === "request_revision" && !kind)) { fail("请本人明确选择建议或决定；要求修回时还需选择小修或大修。"); return; }
    if (rationale.trim().length < 20 || letter.trim().length < 20) { fail("内部依据和给作者的正式决定信都至少需要 20 个字符。"); return; }
    if (recommendationAction) { void prepare("recommend_decision", { recommendation: code, revision_kind: code === "request_revision" ? kind : null, rationale_private: rationale.trim(), author_letter: letter.trim() }); return; }
    if (shareIds.length && !shareReviewed) { fail("请先检查拟分享的意见正文没有审稿人身份或保密内容，再明确勾选分享检查声明。"); return; }
    const due = Number(dueDays);
    if (code === "request_revision" && (instructions.trim().length < 20 || !Number.isInteger(due) || due < 1 || due > 90)) { fail("正式修回要求至少 20 个字符，修回期限为 1 至 90 天。"); return; }
    void prepare("record_decision", { decision_code: code, revision_kind: code === "request_revision" ? kind : null, rationale_private: rationale.trim(), author_letter: letter.trim(), share_report_ids: shareIds, share_reports_anonymity_reviewed: shareReviewed, author_instructions: code === "request_revision" ? instructions.trim() : "", due_days: code === "request_revision" ? due : null });
  }
  function prepareAssessment() {
    if (!outcome || !editorial.revision_request) { fail("请明确选择本次修回复核结果。"); return; }
    if (notes.trim().length < 20) { fail("修回复核意见至少需要 20 个字符。"); return; }
    if (!currentReviewed || !responseReviewed) { fail("请人工检查当前稿件版本及修回说明，再分别勾选声明。"); return; }
    if (editorial.revision_request.kind === "major" && outcome !== "rereview") { fail("正式大修必须重新同行评审，不能直接转入主编决定。"); return; }
    if (outcome === "rereview" && !anonymousReviewed) { fail("重新送审前必须明确检查匿名材料。"); return; }
    void prepare("assess_revision", { outcome, notes: notes.trim(), declarations: { reviewed_current_version: currentReviewed, reviewed_response: responseReviewed, anonymous_material_reviewed: anonymousReviewed } });
  }
  if (!decisionForm && !assessmentAction && !editorial.recommendation && !editorial.assessment && !editorial.reports.length && !editorial.decisions.length) return null;
  return <section className={styles.section} aria-label="编辑决定与修回复核"><h2>{decisionAction ? "主编决定" : recommendationAction ? "责任编辑建议" : assessmentAction ? "正式修回复核" : "编辑依据"}</h2>
    {error && <div role="alert" className={styles.error} tabIndex={-1} ref={errorRef}>{error}<button onClick={() => void refresh()} disabled={busy}>重新载入当前材料</button></div>}
    {editorial.decisions.length > 0 && <section className={styles.section} aria-label="已确认主编决定历史"><h2>已确认主编决定</h2>{editorial.decisions.map(decision => <section className={styles.section} key={decision.id}><h3>{decisionLabels[decision.decision_code]}{decision.revision_kind ? ` · ${revisionLabels[decision.revision_kind]}` : ""}</h3><p className={styles.subtle}>{dateText(decision.decided_at)} · {detail.versions.find(version => version.id === decision.version_id) ? `第 ${detail.versions.find(version => version.id === decision.version_id)!.version_no} 版` : decision.version_id}</p><div className={styles.snapshot}><dl><dt>内部决定依据</dt><dd className={styles.preserve}>{decision.rationale_private}</dd><dt>已确认的给作者决定信</dt><dd className={styles.preserve}>{decision.author_letter}</dd><dt>依据评审轮次</dt><dd>{detail.review?.mode === "staff" && detail.review.round?.id === decision.basis_round_id ? `第 ${detail.review.round.round_no} 轮` : decision.basis_round_id}</dd></dl></div></section>)}</section>}
    {editorial.recommendation && <details className={styles.section} open={!!decisionAction}><summary>已确认的编辑建议 · {decisionLabels[editorial.recommendation.recommendation]}</summary><RecommendationDetails recommendation={editorial.recommendation} /></details>}
    {editorial.assessment && <details className={styles.section}><summary>已确认的本版修回复核</summary><AssessmentDetails assessment={editorial.assessment} /></details>}
    {decisionForm && <form onSubmit={event => { event.preventDefault(); prepareDecision(); }} noValidate><fieldset className={styles.fields} disabled={busy}><div className={styles.fieldControl}><label htmlFor="editorial-decision-code">{recommendationAction ? "编辑建议" : "主编决定"}</label><select id="editorial-decision-code" name={recommendationAction ? "recommendation" : "decision_code"} value={code} onChange={event => { setCode(event.target.value as typeof code); edited(); }}><option value="">请由本人明确选择</option><option value="request_revision">{recommendationAction ? "建议要求修回" : "要求作者修回"}</option><option value="accept">{recommendationAction ? "建议录用" : "录用本稿件"}</option><option value="reject">{recommendationAction ? "建议拒稿" : "拒绝本稿件"}</option></select></div>
      {code === "request_revision" && <div className={styles.fieldControl}><label htmlFor="editorial-revision-kind">修回类型</label><select id="editorial-revision-kind" name="revision_kind" value={kind} onChange={event => { setKind(event.target.value as typeof kind); edited(); }}><option value="">请明确选择</option><option value="minor">小修</option><option value="major">大修并重新同行评审</option></select></div>}
      <div className={styles.fieldControl}><label htmlFor="editorial-rationale">内部决定依据</label><textarea id="editorial-rationale" name="rationale_private" autoComplete="off" rows={5} maxLength={8000} value={rationale} onChange={event => { setRationale(event.target.value); edited(); }} /><p className={styles.subtle}>至少 20 个字符，仅授权编辑与主编可见。</p></div><div className={styles.fieldControl}><label htmlFor="editorial-author-letter">{recommendationAction ? "给作者的决定信建议稿" : "给作者的正式决定信"}</label><textarea id="editorial-author-letter" name="author_letter" autoComplete="off" rows={6} maxLength={12000} value={letter} onChange={event => { setLetter(event.target.value); edited(); }} /><p className={styles.subtle}>{recommendationAction ? "至少 20 个字符，仅随编辑建议交主编审核，尚不向作者发布。" : "至少 20 个字符。主编确认决定后在站内向作者展示，不发送邮件。"}</p></div>
      {decisionAction && code === "request_revision" && <><div className={styles.fieldControl}><label htmlFor="editorial-revision-instructions">正式修回要求</label><textarea id="editorial-revision-instructions" name="author_instructions" autoComplete="off" rows={4} maxLength={12000} value={instructions} onChange={event => { setInstructions(event.target.value); edited(); }} /></div><label htmlFor="editorial-revision-days">修回期限（天）<input id="editorial-revision-days" name="due_days" type="number" min={1} max={90} value={dueDays} onChange={event => { setDueDays(event.target.value); edited(); }} /></label></>}
      {decisionAction && <fieldset className={styles.fields}><legend>向作者共享的匿名评审意见</legend><p className={styles.subtle}>默认不共享。只共享下列作者反馈内容，推荐意见、审稿人身份和编辑保密字段不会加入分享快照。</p>{editorial.reports.map((report, index) => { const authorSnapshot: AuthorReportSnapshot = { author_text: report.author_text, answers: Object.fromEntries(report.form.questions.filter(question => question.audience === "author").map(question => [question.key, report.answers_json[question.key] ?? ""])), questions: report.form.questions.filter(question => question.audience === "author").map(({ key, label, kind, required }) => ({ key, label, kind, required })) }; return <section key={report.id} className={styles.section}><label className={styles.checkbox}><input type="checkbox" name="share_report_ids" value={report.id} checked={shareIds.includes(report.id)} onChange={event => { setShareIds(previous => event.target.checked ? [...previous, report.id] : previous.filter(id => id !== report.id)); setShareReviewed(false); edited(); }} />向作者共享第 {index + 1} 份匿名评审意见</label><AnonymousAuthorReport snapshot={authorSnapshot} /></section>; })}{!editorial.reports.length && <p>当前没有可共享的已提交报告。</p>}{shareIds.length > 0 && <label className={styles.checkbox}><input name="share_reports_anonymity_reviewed" type="checkbox" checked={shareReviewed} onChange={event => { setShareReviewed(event.target.checked); edited(); }} />已检查拟分享意见正文不含审稿人身份和保密内容</label>}</fieldset>}
      <button type="submit">{busy ? "正在准备…" : decisionForm.label}</button>
    </fieldset></form>}
    {assessmentAction && <form onSubmit={event => { event.preventDefault(); prepareAssessment(); }} noValidate><fieldset className={styles.fields} disabled={busy}>{editorial.revision_request && <p className={styles.notice}>第 {editorial.revision_request.request_no} 次正式修回 · {revisionLabels[editorial.revision_request.kind]}{editorial.revision_request.rereview_required ? "；需要重新同行评审。" : "；可明确复核后形成新的编辑建议。"}</p>}<div className={styles.fieldControl}><label htmlFor="revision-assessment-outcome">修回复核结果</label><select id="revision-assessment-outcome" name="outcome" value={outcome} onChange={event => { setOutcome(event.target.value as typeof outcome); edited(); }}><option value="">请由责任编辑明确选择</option>{editorial.revision_request?.kind !== "major" && <option value="ready_for_chief">完成复核，重新形成编辑建议</option>}<option value="rereview">重新送交同行评审</option></select></div><div className={styles.fieldControl}><label htmlFor="revision-assessment-notes">修回复核意见</label><textarea id="revision-assessment-notes" name="notes" autoComplete="off" rows={5} maxLength={8000} value={notes} onChange={event => { setNotes(event.target.value); edited(); }} /></div><label className={styles.checkbox}><input type="checkbox" name="reviewed_current_version" checked={currentReviewed} onChange={event => { setCurrentReviewed(event.target.checked); edited(); }} />我已人工检查当前修回版本</label><label className={styles.checkbox}><input type="checkbox" name="reviewed_response" checked={responseReviewed} onChange={event => { setResponseReviewed(event.target.checked); edited(); }} />我已人工阅读本次修回说明</label>{outcome === "rereview" && <label className={styles.checkbox}><input type="checkbox" name="anonymous_material_reviewed" checked={anonymousReviewed} onChange={event => { setAnonymousReviewed(event.target.checked); edited(); }} />我已人工检查重新送审的匿名材料</label>}<button>{busy ? "正在准备…" : assessmentAction.label}</button></fieldset></form>}
    {reviewURL && <p role="status"><Link href={reviewURL} className={styles.actionLink}>打开完整资料并由负责人确认</Link></p>}
    {editorial.reports.length > 0 && <section className={styles.section}><h2>决定依据中的已提交评审报告</h2>{editorial.reports.map((report, index) => <details key={report.id} className={styles.section}><summary>报告 {index + 1} · {report.reviewer_name} · 已提交于 {dateText(report.submitted_at)}</summary><ReviewReportContent report={report} form={report.form} /><p className={styles.hash}>报告 SHA-256：<code>{report.content_digest}</code></p></details>)}</section>}
  </section>;
}

function RecommendationDetails({ recommendation }: { recommendation: RecommendationSnapshot }) {
  return <div className={styles.snapshot}><dl><dt>编辑建议</dt><dd>{decisionLabels[recommendation.recommendation]}{recommendation.revision_kind ? ` · ${revisionLabels[recommendation.revision_kind]}` : ""}（尚非主编决定）</dd><dt>内部依据</dt><dd className={styles.preserve}>{recommendation.rationale_private}</dd><dt>给作者的决定信草稿</dt><dd className={styles.preserve}>{recommendation.author_letter}</dd></dl><p className={styles.subtle}>依据 {recommendation.report_digests.length} 份已提交报告。</p><ul className={styles.files}>{recommendation.report_digests.map(report => <li key={report.report_id}><code>报告 SHA-256 {report.content_digest}</code><code>表单 SHA-256 {report.form_digest}</code></li>)}</ul></div>;
}

function AssessmentDetails({ assessment }: { assessment: AssessmentSnapshot }) {
  return <div className={styles.snapshot}><dl><dt>复核结果</dt><dd>{assessment.outcome === "ready_for_chief" ? "完成复核，重新形成编辑建议" : "重新送交同行评审"}</dd><dt>修回复核意见</dt><dd className={styles.preserve}>{assessment.notes}</dd></dl><ul className={styles.missing}><li>{assessment.declarations.reviewed_current_version ? "已人工检查当前修回版本" : "未声明已检查当前版本"}</li><li>{assessment.declarations.reviewed_response ? "已人工阅读本次修回说明" : "未声明已阅读修回说明"}</li>{assessment.outcome === "rereview" && <li>{assessment.declarations.anonymous_material_reviewed ? "已人工检查重新送审的匿名材料" : "未声明已检查匿名材料"}</li>}</ul><p className={styles.hash}>修回说明 SHA-256：<code>{assessment.response_file.sha256}</code></p></div>;
}

function DecisionDetails({ decision }: { decision: DecisionSnapshot }) {
  return <section className={styles.snapshot} aria-label="拟确认的主编决定"><h2>{decisionLabels[decision.decision_code]}{decision.revision_kind ? ` · ${revisionLabels[decision.revision_kind]}` : ""}</h2><dl><dt>内部决定依据</dt><dd className={styles.preserve}>{decision.rationale_private}</dd><dt>给作者的正式决定信</dt><dd className={styles.preserve}>{decision.author_letter}</dd></dl>{decision.revision_request && <section className={styles.notice}><h3>第 {decision.revision_request.request_no} 次正式修回</h3><p className={styles.preserve}>{decision.revision_request.author_instructions}</p><p>截止时间：{dateText(decision.revision_request.due_at)}；{revisionLabels[decision.revision_request.kind]}{decision.revision_request.rereview_required ? "，需要重新同行评审" : ""}。</p><p>确认后建立新作者准备版本，保留本次原稿与历史报告。</p></section>}{decision.production_assignee && <section className={styles.notice}><h3>出版制作负责人</h3><p>{decision.production_assignee.name} · {decision.production_assignee.email}</p><p>出版编辑；确认录用后创建此负责人的出版制作待办，不发送邮件或公开发布。</p></section>}<h3>将向作者共享的匿名评审意见</h3>{decision.public_reports.length ? <><p>{decision.share_reports_anonymity_reviewed ? "负责人已声明检查拟分享正文不含审稿人身份和保密内容；这项声明不代表系统自动保证匿名。" : "未声明已检查拟分享正文的匿名与保密内容。"}</p>{decision.public_reports.map(report => <section className={styles.section} key={report.ordinal}><h3>匿名评审意见 {report.ordinal}</h3><AnonymousAuthorReport snapshot={report.author_snapshot} /><p className={styles.hash}>分享快照 SHA-256：<code>{report.snapshot_digest}</code></p></section>)}</> : <p>本次不向作者共享评审报告。</p>}</section>;
}

export function EditorialSnapshot({ proposal }: { proposal: Proposal }) {
  if (proposal.action_type === "recommend_decision" && proposal.payload.recommendation) return <section aria-label="拟确认的编辑建议"><h2>编辑建议审核</h2><RecommendationDetails recommendation={proposal.payload.recommendation} /></section>;
  if (proposal.action_type === "record_decision" && proposal.payload.decision) return <><DecisionDetails decision={proposal.payload.decision} />{proposal.payload.decision_digest && <p className={styles.hash}>决定 SHA-256：<code>{proposal.payload.decision_digest}</code></p>}</>;
  if (proposal.action_type === "submit_revision" && proposal.payload.revision_request) { const request = proposal.payload.revision_request; return <section className={styles.snapshot} aria-label="拟提交的正式修回"><h2>{request.request_no ? `第 ${request.request_no} 次正式修回提交` : "正式修回提交"}</h2><p className={styles.preserve}>{request.author_instructions}</p><p>{revisionLabels[request.kind]} · 截止 {dateText(request.due_at)}{request.rereview_required ? " · 需重新同行评审" : ""}</p><p>确认后冻结以下当前修回版本及实际修回说明文件，交由责任编辑复核。</p></section>; }
  if (proposal.action_type === "assess_revision" && proposal.payload.assessment) return <section aria-label="拟确认的修回复核"><h2>正式修回复核审核</h2><AssessmentDetails assessment={proposal.payload.assessment} /></section>;
  return null;
}

export function editorialConfirmationLabel(proposal: Proposal): string | null {
  if (proposal.action_type === "recommend_decision") return "确认并提交编辑建议";
  if (proposal.action_type === "record_decision") return proposal.payload.decision?.decision_code === "request_revision" ? "确认要求作者修回" : proposal.payload.decision?.decision_code === "accept" ? "确认录用本稿件" : "确认拒绝本稿件";
  if (proposal.action_type === "submit_revision") return "确认并提交正式修回";
  if (proposal.action_type === "assess_revision") return proposal.payload.assessment?.outcome === "ready_for_chief" ? "确认复核并进入编辑建议" : "确认复核并转入重新送审";
  return null;
}
