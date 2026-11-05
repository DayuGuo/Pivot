"use client";
import { warnBeforeUnload } from "../browser";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Detail, ProductionMetadata, ProductionProjection, ProofFileSnapshot, ProofPackageDTO } from "./types";
import { dateText } from "./types";
import { Files } from "./intake";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

export function proofFileURL(file: ProofFileSnapshot): string | undefined {
  return file.download_url && /^\/api\/publishing\/(?:proof-packages\/[0-9a-f-]{36}\/file|manuscripts\/[0-9a-f-]{36}\/proof-files\/[0-9a-f-]{36})$/.test(file.download_url) ? file.download_url : undefined;
}
export function previewPageURL(url: string): string | undefined { return /^\/publishing\/preview\/[0-9a-f-]{36}$/.test(url) ? url : undefined; }

export function ProductionMetadataView({ metadata }: { metadata: ProductionMetadata }) {
  return <section className={styles.snapshot} aria-label="冻结录用元数据"><dl><dt>题名</dt><dd>{metadata.title}</dd><dt>摘要</dt><dd className={styles.preserve}>{metadata.abstract}</dd><dt>语言与文章类型</dt><dd>{metadata.language === "zh" ? "中文" : "英文"} · 研究论文</dd><dt>关键词</dt><dd>{metadata.keywords.join("、")}</dd><dt>作者署名顺序</dt><dd><ol className={styles.snapshotAuthors}>{metadata.authors.map((author, index) => <li key={index}><strong>{author.name}{author.corresponding ? "（通讯作者）" : ""}</strong>{author.orcid && <span>ORCID {author.orcid} · 格式信息，未核实身份</span>}<span>单位：{author.affiliations.join("；") || "未提供"}</span><span>贡献：{author.contributions.join("；") || "未提供"}</span></li>)}</ol></dd><dt>基金资助</dt><dd className={styles.preserve}>{metadata.funding_statement || "未提供"}</dd></dl></section>;
}

export function ProofFileView({ file, downloadURL }: { file: ProofFileSnapshot; downloadURL?: string }) {
  const url = proofFileURL({ ...file, download_url: downloadURL ?? file.download_url });
  return <div className={styles.files}>{url ? <a href={url} download>{file.filename}</a> : <strong>{file.filename}</strong>}<p className={styles.subtle}>{new Intl.NumberFormat("zh-CN").format(file.byte_size)} 字节 · {file.media_type}</p><p className={styles.hash}>文件 SHA-256：<code>{file.sha256}</code></p>{file.check_method && <p className={styles.subtle}>检查：{file.check_method} · {file.scan_status}；未执行病毒扫描。</p>}</div>;
}

function PackageView({ item }: { item: ProofPackageDTO }) {
  return <div><ProofFileView file={item.file} /><p className={styles.hash}>校样包 SHA-256：<code>{item.material_digest}</code></p>{item.response ? <div className={item.response.outcome === "approve" ? styles.success : styles.notice}><strong>{item.response.outcome === "approve" ? "作者已通过本包校样" : "作者要求更正本包正文"}</strong>{item.response.notes && <p className={styles.preserve}>{item.response.notes}</p>}<p>{dateText(item.response.responded_at)}</p></div> : <p className={styles.subtle}>等待作者本人校样回应。</p>}</div>;
}

export default function ProductionWork({ detail, production }: { detail: Detail; production: ProductionProjection }) {
  const { mutate, refresh, setUnsaved } = usePublishing();
  const [file, setFile] = useState<File | null>(null); const [outcome, setOutcome] = useState<"" | "approve" | "request_corrections">(""); const [notes, setNotes] = useState("");
  const [metadataReviewed, setMetadataReviewed] = useState(false); const [proofReviewed, setProofReviewed] = useState(false); const [approvedReviewed, setApprovedReviewed] = useState(false);
  const [baseRevision, setBaseRevision] = useState(detail.revision); const [busy, setBusy] = useState(false); const [dirty, setDirty] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [reviewURL, setReviewURL] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null); const errorRef = useRef<HTMLDivElement>(null);
  const active = production.packages.find(item => item.id === production.active_package_id);
  const unchangedCorrection = production.mode === "production" && active?.response?.outcome === "request_corrections" && production.draft_file?.sha256 === active.file.sha256;
  const sendAction = detail.allowed_actions.find(action => action.action === "send_proof"); const responseAction = detail.allowed_actions.find(action => action.action === "confirm_proof"); const previewAction = detail.allowed_actions.find(action => action.action === "prepare_local_preview");
  useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
  useEffect(() => { if (!dirty) return; const warn = warnBeforeUnload; window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  if (baseRevision !== detail.revision) { setBaseRevision(detail.revision); setMetadataReviewed(false); setProofReviewed(false); setApprovedReviewed(false); setReviewURL(null); }
  function edited() { setDirty(true); setReviewURL(null); setNotice(""); }
  function fail(message: string) { setError(message); requestAnimationFrame(() => errorRef.current?.focus()); }
  async function upload() {
    if (production.mode !== "production" || !production.can_upload_proof) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (!file || !/\.(txt|md)$/i.test(file.name) || file.size < 1 || file.size > 1048576) throw new Error("请选择 1 字节至 1 MiB 的 UTF-8 TXT 或 Markdown 正文校样。");
      const bytes = new Uint8Array(await file.arrayBuffer()); try { new TextDecoder("utf-8", { fatal: true }).decode(bytes); } catch { throw new Error("校样不是有效 UTF-8 文本，请重新导出后上传。"); }
      let binary = ""; for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      await mutate(`/manuscripts/${detail.id}/proof-files`, { expected_revision: detail.revision, file: { filename: file.name, content_base64: btoa(binary), purpose: "proof" } });
      setFile(null); if (input.current) input.current.value = ""; setDirty(false); setUnsaved(false); setNotice("私人校样文件已保存，尚未交作者确认。"); await refresh();
    } catch (failure) { fail((failure as Error).message); if (failure instanceof APIError && failure.status === 409) await refresh(); }
    finally { setBusy(false); }
  }
  async function prepare(action: string, data: object) {
    if (!detail.allowed_actions.some(item => item.action === action)) { fail("当前账号无权执行此操作，请重新载入。"); return; }
    setBusy(true); setError(""); setReviewURL(null);
    try { const result = await mutate<{ proposal_id: string }>(`/manuscripts/${detail.id}/proposals`, { expected_revision: detail.revision, action_type: action, data }); setReviewURL(`/publishing/review/${result.proposal_id}`); setDirty(false); setUnsaved(false); }
    catch (failure) { fail((failure as Error).message); if (failure instanceof APIError && failure.status === 409) await refresh(); }
    finally { setBusy(false); }
  }
  function send() { if (unchangedCorrection) { fail("作者要求正文更正，请先上传内容不同的新校样，再准备交作者审核。"); return; } if (file) { fail("请先上传并保存所选校样文件，再准备交作者审核。"); return; } if (!metadataReviewed || !proofReviewed) { fail("请人工核对冻结元数据与本次正文校样，再分别勾选声明。"); return; } void prepare("send_proof", { declarations: { metadata_reviewed: metadataReviewed, proof_reviewed: proofReviewed } }); }
  function respond() { if (!active || !outcome || !proofReviewed) { fail("请阅读当前指定校样包，明确选择结果并勾选已阅读声明。"); return; } if (outcome === "request_corrections" && notes.trim().length < 20) { fail("要求正文更正时，请至少用 20 个字符说明需要修改的内容。"); return; } void prepare("confirm_proof", { package_id: active.id, outcome, notes: notes.trim(), declarations: { proof_reviewed: proofReviewed } }); }
  function preview() { if (!active || active.response?.outcome !== "approve" || !metadataReviewed || !approvedReviewed) { fail("请核对作者已通过的当前指定校样包及冻结元数据，并明确勾选声明。"); return; } void prepare("prepare_local_preview", { declarations: { metadata_reviewed: metadataReviewed, approved_proof_reviewed: approvedReviewed } }); }
  return <section className={styles.panel} aria-label="校样与本地预览"><h2>{responseAction ? "作者校样" : previewAction ? "准备鉴权本地预览" : production.preview ? "已生成本地预览" : "正文校样制作"}</h2><p className={styles.notice}>录用元数据已冻结。本阶段只更正正文校样；生成本地预览不等于正式发表。</p>
    {error && <div role="alert" ref={errorRef} tabIndex={-1} className={styles.error}>{error}<button disabled={busy} onClick={() => void refresh()}>重新载入当前校样</button></div>}<p className={styles.saved} aria-live="polite">{notice}</p>
    {production.mode === "production" && production.accepted_materials.length > 0 && <details className={styles.section}><summary>录用版源正文</summary><Files files={production.accepted_materials} /></details>}
    {production.mode === "production" && production.can_upload_proof && <section className={styles.fields}><label htmlFor="production-proof-upload">正文校样文件<input ref={input} id="production-proof-upload" name="proof" type="file" accept=".txt,.md,text/plain,text/markdown" disabled={busy} onChange={event => { setFile(event.target.files?.[0] ?? null); edited(); }} /></label><p className={styles.subtle}>UTF-8 TXT / Markdown，单个不超过 1 MiB。上传不改变题名、署名、摘要等冻结元数据。</p><button disabled={busy || !file} onClick={() => void upload()}>{busy ? "处理中…" : "上传并保存正文校样"}</button>{production.draft_file && <div><h3>当前私人校样草稿</h3><ProofFileView file={production.draft_file} /></div>}</section>}
    {active && <section className={styles.section} aria-label="当前指定校样包"><h3>当前指定校样包 {active.package_no}</h3><PackageView item={active} /></section>}
    {unchangedCorrection && <p className={styles.notice}>作者要求正文更正，请上传内容不同的新校样；已有校样包和作者意见会保留。</p>}
    {sendAction && production.mode === "production" && <form onSubmit={event => { event.preventDefault(); send(); }}><fieldset className={styles.fields} disabled={busy}><label className={styles.checkbox}><input type="checkbox" name="metadata_reviewed" checked={metadataReviewed} onChange={event => { setMetadataReviewed(event.target.checked); edited(); }} />我已核对冻结的录用元数据</label><label className={styles.checkbox}><input type="checkbox" name="proof_reviewed" checked={proofReviewed} onChange={event => { setProofReviewed(event.target.checked); edited(); }} />我已人工阅读本次正文校样</label><button disabled={!production.draft_file || !!file || unchangedCorrection}>{busy ? "正在准备…" : sendAction.label}</button></fieldset></form>}
    {responseAction && production.mode === "author" && <form onSubmit={event => { event.preventDefault(); respond(); }}><fieldset className={styles.fields} disabled={busy}><div className={styles.fieldControl}><label htmlFor="proof-response-outcome">本包校样结果</label><select id="proof-response-outcome" name="outcome" value={outcome} onChange={event => { setOutcome(event.target.value as typeof outcome); edited(); }}><option value="">请由作者本人明确选择</option><option value="approve">通过本包校样</option><option value="request_corrections">要求正文更正</option></select></div><div className={styles.fieldControl}><label htmlFor="proof-response-notes">校样意见</label><textarea id="proof-response-notes" name="notes" autoComplete="off" rows={4} maxLength={4000} value={notes} onChange={event => { setNotes(event.target.value); edited(); }} /></div><label className={styles.checkbox}><input type="checkbox" name="proof_reviewed" checked={proofReviewed} onChange={event => { setProofReviewed(event.target.checked); edited(); }} />我已阅读当前指定包的实际正文校样</label><button disabled={!active}>{busy ? "正在准备…" : responseAction.label}</button></fieldset></form>}
    {previewAction && production.mode === "production" && <form onSubmit={event => { event.preventDefault(); preview(); }}><fieldset className={styles.fields} disabled={busy}><label className={styles.checkbox}><input type="checkbox" name="metadata_reviewed" checked={metadataReviewed} onChange={event => { setMetadataReviewed(event.target.checked); edited(); }} />我已核对冻结的录用元数据</label><label className={styles.checkbox}><input type="checkbox" name="approved_proof_reviewed" checked={approvedReviewed} onChange={event => { setApprovedReviewed(event.target.checked); edited(); }} />我已核对作者通过的确切校样包</label><button disabled={!active}>{busy ? "正在准备…" : previewAction.label}</button></fieldset></form>}
    {reviewURL && <p role="status"><Link className={styles.actionLink} href={reviewURL}>打开完整资料并由负责人确认</Link></p>}
    {production.preview && previewPageURL(production.preview.url) && <p><Link className={styles.actionLink} href={previewPageURL(production.preview.url)!}>打开鉴权本地预览</Link><span className={styles.subtle}> · 尚未正式发表</span></p>}
    <details className={styles.section}><summary>冻结录用元数据</summary><ProductionMetadataView metadata={production.metadata_snapshot} /><p className={styles.hash}>元数据 SHA-256：<code>{production.metadata_digest}</code></p></details>
    {production.packages.length > 0 && <details className={styles.section}><summary>校样包与作者回应历史 · {production.packages.length}</summary>{production.packages.map(item => <section className={styles.section} key={item.id}><h3>校样包 {item.package_no}</h3><p className={styles.subtle}>{dateText(item.created_at)}</p><PackageView item={item} /></section>)}</details>}
  </section>;
}
