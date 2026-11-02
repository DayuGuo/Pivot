"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { CheckDeclarations, Detail, Proposal, StaffReport } from "./types";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

export const stageLabels: Record<string, string> = {
  precheck_completeness: "材料完整性预审", similarity_review: "相似度报告人工复核",
  technical_screening: "匿名材料筛选", chief_scope: "主编范围初筛",
  assign_editor: "分派责任编辑", editor_quality: "责任编辑质量评估",
};
const emptyDeclarations = (): CheckDeclarations => ({ materials_reviewed: false, report_reviewed: false, anonymous_material_reviewed: false, scope_matches: null, quality_sufficient: null });

export function StageActions({ detail }: { detail: Detail }) {
  const { mutate, refresh, setUnsaved } = usePublishing();
  const [outcome, setOutcome] = useState<"" | "pass" | "return">("");
  const [notes, setNotes] = useState(""); const [reason, setReason] = useState("");
  const [editorId, setEditorId] = useState(""); const [declarations, setDeclarations] = useState(emptyDeclarations);
  const [baseRevision, setBaseRevision] = useState(detail.revision); const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [reviewURL, setReviewURL] = useState<string | null>(null); const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null); const errorBox = useRef<HTMLDivElement>(null);
  const staff = detail.staff_review;
  const action = detail.allowed_actions.find(item => item.action === (staff?.kind === "assign_editor" ? "assign_editor" : "record_check"));
  useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
  useEffect(() => { if (!dirty) return; function warn(event: BeforeUnloadEvent) { event.preventDefault(); } window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  if (detail.revision !== baseRevision) {
    setBaseRevision(detail.revision); setDeclarations(emptyDeclarations()); setReviewURL(null);
    setNotice("稿件材料已更新，请重新核对后勾选人工复核声明。");
  }
  if (!staff || !action) return null;
  const assignment = staff.kind === "assign_editor";
  function edited() { setDirty(true); setReviewURL(null); setNotice(""); }
  function checked(key: keyof CheckDeclarations, value: boolean) { setDeclarations(previous => ({ ...previous, [key]: value })); edited(); }
  function fail(failure: unknown) {
    setError((failure as Error).message); requestAnimationFrame(() => errorBox.current?.focus());
  }
  async function upload() {
    setBusy(true); setError(""); setNotice("");
    try {
      if (!file || !/\.(txt|md)$/i.test(file.name) || file.size < 1 || file.size > 1048576) throw new Error("请选择 1 字节至 1 MiB 的 UTF-8 TXT 或 Markdown 报告。");
      const bytes = new Uint8Array(await file.arrayBuffer());
      try { new TextDecoder("utf-8", { fatal: true }).decode(bytes); } catch { throw new Error("报告不是有效 UTF-8 文本，请重新导出后上传。"); }
      let binary = ""; for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
      await mutate(`/manuscripts/${detail.id}/reports`, { expected_revision: detail.revision, file: { filename: file.name, content_base64: btoa(binary), purpose: "similarity_report" } });
      setFile(null); if (fileInput.current) fileInput.current.value = ""; await refresh();
    } catch (failure) { fail(failure); } finally { setBusy(false); }
  }
  async function prepare() {
    if (!staff || !action) return;
    setError("");
    if (!notes.trim()) { fail(new Error("请填写本关口的人工检查意见或分派说明。")); return; }
    if (assignment && !editorId) { fail(new Error("请选择一位有资格的责任编辑。")); return; }
    if (!assignment) {
      if (!outcome) { fail(new Error("请明确选择通过或退回作者修改。")); return; }
      if (outcome === "return" && !reason.trim()) { fail(new Error("退回作者修改必须说明原因。")); return; }
      if (!declarations.materials_reviewed) { fail(new Error("请先人工检查材料，再勾选复核声明。")); return; }
      if (staff.kind === "similarity_review" && (!staff.report || !declarations.report_reviewed)) { fail(new Error("请上传真实报告，并明确确认已人工阅读报告；系统不会自动查重。")); return; }
      if (outcome === "pass" && staff.kind === "technical_screening" && !declarations.anonymous_material_reviewed) { fail(new Error("通过前必须人工检查匿名稿件。")); return; }
      if (outcome === "pass" && staff.kind === "chief_scope" && declarations.scope_matches !== true) { fail(new Error("通过前必须由主编确认符合受稿范围。")); return; }
      if (outcome === "pass" && staff.kind === "editor_quality" && declarations.quality_sufficient !== true) { fail(new Error("通过前必须由责任编辑确认质量适合送审。")); return; }
    }
    const evidence: CheckDeclarations = { materials_reviewed: declarations.materials_reviewed };
    if (staff.kind === "similarity_review") evidence.report_reviewed = declarations.report_reviewed;
    if (staff.kind === "technical_screening") evidence.anonymous_material_reviewed = declarations.anonymous_material_reviewed;
    if (staff.kind === "chief_scope") evidence.scope_matches = declarations.scope_matches;
    if (staff.kind === "editor_quality") evidence.quality_sufficient = declarations.quality_sufficient;
    const data = assignment ? { editor_id: editorId, notes: notes.trim() } : { outcome, notes: notes.trim(), reason: outcome === "return" ? reason.trim() : "", file_object_id: staff.kind === "similarity_review" ? staff.report?.id ?? null : null, declarations: evidence };
    setBusy(true);
    try {
      const result = await mutate<{ proposal_id: string }>(`/manuscripts/${detail.id}/proposals`, { expected_revision: detail.revision, action_type: action.action, data });
      setReviewURL(`/publishing/review/${result.proposal_id}`); setDirty(false); setUnsaved(false);
      setNotice("审核快照已准备，尚未执行；请打开独立审核页确认。");
    } catch (failure) { fail(failure); if (failure instanceof APIError && failure.status === 409) await refresh(); }
    finally { setBusy(false); }
  }
  return <section className={styles.section} aria-label="当前负责人操作"><h2>{stageLabels[staff.kind] ?? detail.stage_label}</h2>
    {error && <div ref={errorBox} tabIndex={-1} className={styles.error} role="alert">{error}<button onClick={() => void refresh()} disabled={busy}>重新载入当前材料</button></div>}
    <p className={styles.saved} aria-live="polite">{notice}</p>
    {!assignment && staff.note_candidates && <section className={styles.notice} aria-label="AI 检查意见候选"><h3>AI 检查意见候选 · 未核实</h3><p className={styles.preserve}>{staff.note_candidates.notes}</p>{staff.note_candidates.reason && <p className={styles.preserve}>退回原因候选：{staff.note_candidates.reason}</p>}<p>请核对候选内容；采用只填写意见和原因，检查结果与人工复核声明仍由你决定。</p><button type="button" disabled={busy || !!notes.trim()} onClick={() => { if (!staff.note_candidates || notes.trim()) return; setNotes(staff.note_candidates.notes); setReason(staff.note_candidates.reason); edited(); }}>采用检查意见候选</button>{!!notes.trim() && <p>当前已有人工检查意见，已保留。你可以选择并复制需要的候选文本。</p>}</section>}
    {staff.kind === "similarity_review" && <div className={styles.fields}><p className={styles.subtle}>本关口为人工阅读查重报告，不运行自动查重或生成检测结论。报告仅向获授权的工作人员开放。</p>{staff.report && <ReportEvidence report={staff.report} />}<label htmlFor="similarity-report-file">查重报告文件<input ref={fileInput} id="similarity-report-file" name="similarity_report" type="file" accept=".txt,.md,text/plain,text/markdown" disabled={busy} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label><p className={styles.subtle}>UTF-8 TXT / Markdown，单个不超过 1 MiB。</p><button onClick={() => void upload()} disabled={busy || !file}>{busy ? "处理中…" : staff.report ? "替换并保存报告" : "上传并保存报告"}</button></div>}
    <form onSubmit={event => { event.preventDefault(); void prepare(); }} noValidate><fieldset className={styles.fields} disabled={busy}>
      {assignment ? <div className={styles.fieldControl}><label htmlFor="handling-editor">责任编辑</label><select id="handling-editor" name="editor_id" value={editorId} onChange={event => { setEditorId(event.target.value); edited(); }}><option value="">请选择责任编辑</option>{staff.eligible_editors.map(editor => <option key={editor.id} value={editor.id}>{editor.name} · {editor.email}</option>)}</select>{!staff.eligible_editors.length && <p className={styles.notice}>当前没有符合条件的本刊编辑，请由期刊负责人检查成员与利益冲突配置。</p>}</div> : <div className={styles.fieldControl}><label htmlFor="screening-outcome">检查结果</label><select id="screening-outcome" name="outcome" value={outcome} onChange={event => { setOutcome(event.target.value as "" | "pass" | "return"); edited(); }}><option value="">请由负责人选择</option><option value="pass">通过本关口</option><option value="return">退回作者修改</option></select></div>}
      <div className={styles.fieldControl}><label htmlFor="screening-notes">{assignment ? "分派说明" : "人工检查意见"}</label><textarea id="screening-notes" name="notes" autoComplete="off" rows={4} maxLength={4000} value={notes} onChange={event => { setNotes(event.target.value); edited(); }} /></div>
      {!assignment && outcome === "return" && <div className={styles.fieldControl}><label htmlFor="screening-return-reason">退回原因</label><textarea id="screening-return-reason" name="reason" autoComplete="off" rows={3} maxLength={4000} value={reason} onChange={event => { setReason(event.target.value); edited(); }} /></div>}
      {!assignment && <><label className={styles.checkbox}><input name="materials_reviewed" type="checkbox" checked={declarations.materials_reviewed} onChange={event => checked("materials_reviewed", event.target.checked)} />我已人工检查当前版本的稿件材料</label>{staff.kind === "similarity_review" && <label className={styles.checkbox}><input name="report_reviewed" type="checkbox" checked={!!declarations.report_reviewed} onChange={event => checked("report_reviewed", event.target.checked)} />我已人工阅读并复核本次上传的查重报告</label>}{staff.kind === "technical_screening" && <label className={styles.checkbox}><input name="anonymous_material_reviewed" type="checkbox" checked={!!declarations.anonymous_material_reviewed} onChange={event => checked("anonymous_material_reviewed", event.target.checked)} />我已人工检查供审稿人使用的匿名稿件</label>}{staff.kind === "chief_scope" && outcome === "pass" && <label className={styles.checkbox}><input name="scope_matches" type="checkbox" checked={declarations.scope_matches === true} onChange={event => checked("scope_matches", event.target.checked)} />我确认稿件符合本刊受稿范围</label>}{staff.kind === "editor_quality" && outcome === "pass" && <label className={styles.checkbox}><input name="quality_sufficient" type="checkbox" checked={declarations.quality_sufficient === true} onChange={event => checked("quality_sufficient", event.target.checked)} />我确认稿件质量适合送交同行评审</label>}</>}
      <button type="submit" disabled={busy}>{busy ? "正在准备…" : action.label}</button>
    </fieldset></form>{reviewURL && <p><Link className={styles.actionLink} href={reviewURL}>打开完整资料并由负责人确认</Link></p>}
  </section>;
}

export function ReportEvidence({ report }: { report: StaffReport }) {
  const safeURL = /^\/api\/publishing\/manuscripts\/[0-9a-f-]{36}\/reports\/[0-9a-f-]{36}$/.test(report.download_url) ? report.download_url : undefined;
  return <div className={styles.files}><strong>人工复核报告</strong><div>{safeURL ? <a href={safeURL} download>{report.name}</a> : report.name}</div><small>{new Intl.NumberFormat("zh-CN").format(report.byte_size)} 字节 · 文本安全检查：{report.check_method}</small><p className={styles.hash}>SHA-256：<code>{report.sha256}</code></p><p className={styles.subtle}>复核方式：人工复核；报告内容不代表系统自动检测结果。</p></div>;
}

export function StageReviewSummary({ proposal }: { proposal: Proposal }) {
  const { check, editor, report } = proposal.payload;
  if (proposal.action_type === "record_check" && check) return <section className={styles.snapshot} aria-label="拟确认的检查结果"><h2>{stageLabels[check.kind] ?? check.kind}</h2><dl><dt>拟执行结果</dt><dd>{check.outcome === "pass" ? "通过本关口" : "退回作者修改"}</dd><dt>人工检查意见</dt><dd className={styles.preserve}>{check.notes}</dd>{check.reason && <><dt>退回原因</dt><dd className={styles.preserve}>{check.reason}</dd></>}<dt>复核方式</dt><dd>人工复核</dd></dl><h3>负责人的人工复核声明</h3><ul className={styles.missing}><li>{check.evidence_json.declarations.materials_reviewed ? "已人工检查当前版本的稿件材料" : "未声明已检查材料"}</li>{check.kind === "similarity_review" && <li>{check.evidence_json.declarations.report_reviewed ? "已人工阅读并复核上传的查重报告" : "未声明已复核报告"}</li>}{check.kind === "technical_screening" && <li>{check.evidence_json.declarations.anonymous_material_reviewed ? "已人工检查匿名稿件" : "未声明已检查匿名稿件"}</li>}{check.kind === "chief_scope" && <li>{check.evidence_json.declarations.scope_matches === true ? "确认符合本刊受稿范围" : "未声明符合受稿范围"}</li>}{check.kind === "editor_quality" && <li>{check.evidence_json.declarations.quality_sufficient === true ? "确认稿件质量适合送审" : "未声明质量适合送审"}</li>}</ul>{report && <ReportEvidence report={report} />}</section>;
  if (proposal.action_type === "assign_editor" && editor) return <section className={styles.snapshot} aria-label="拟确认的编辑分派"><h2>拟分派责任编辑</h2><dl><dt>责任编辑</dt><dd>{editor.name}</dd><dt>邮箱</dt><dd>{editor.email}</dd><dt>分派说明</dt><dd className={styles.preserve}>{proposal.payload.notes || "未填写"}</dd></dl><p className={styles.subtle}>确认后建立本稿件的编辑责任与质量初筛任务，不发送邮件。</p></section>;
  return null;
}

export function confirmationLabel(proposal: Proposal): string {
  if (proposal.action_type === "submit") return "确认并提交投稿";
  if (proposal.action_type === "assign_editor") return "确认并分派责任编辑";
  if (proposal.action_type === "record_check" && proposal.payload.check) return proposal.payload.check.outcome === "return" ? "确认并退回作者修改" : `确认通过${stageLabels[proposal.payload.check.kind] ?? "本关口"}`;
  return "由我确认并执行";
}
