"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Author, Detail, IntakeData, Version, VersionFile } from "./types";
import { dateText, fileURL, purposeLabels } from "./types";
import { APIError, usePublishing } from "./workspace";
import { StageActions, stageLabels } from "./stage-actions";
import { ReviewerPeerReview, StaffPeerReview } from "./review-work";
import { EditorialActions, EditorialFeedback } from "./decisions";
import styles from "./publishing.module.css";

const newAuthor = (): Author => ({ name: "", email: "", orcid: null, affiliations: [], corresponding: false, contributions: [] });

export function PublishingHome() {
  const { workspace, detail, selectedId, refreshing, refresh, select } = usePublishing();
  if (selectedId && detail?.id !== selectedId) return <section className={styles.panel}><h1>稿件材料</h1><p role="status">{refreshing ? "正在载入…" : "暂时无法打开这篇稿件。请重新载入或返回工作列表。"}</p><button onClick={() => void refresh()} disabled={refreshing}>重新载入</button><button onClick={() => select(null)}>返回工作列表</button></section>;
  if (detail && selectedId) return <Manuscript key={detail.id} detail={detail} />;
  return <section className={styles.panel}><header className={styles.panelHeader}><h1>我的稿件</h1><button onClick={() => void refresh()} disabled={refreshing}>刷新</button></header>{workspace?.submissions.length ? <div className={styles.submissionList}>{workspace.submissions.map(item => <Link key={item.id} href={`/publishing?manuscript=${item.id}`} onClick={event => { event.preventDefault(); select(item.id); }}><div><span>{item.number}</span><span className={styles.status}>{item.stage_label}</span></div><strong>{item.title || "未命名投稿"}</strong>{item.is_legacy && <small>旧版原型记录 · 只读</small>}</Link>)}</div> : <p className={styles.empty}>还没有可查看的稿件。你可以在对话中整理信息，作者也可以从左侧新建投稿。</p>}</section>;
}

function Manuscript({ detail }: { detail: Detail }) {
  if (detail.review?.mode === "reviewer") return <ReviewerPeerReview key={detail.review.invitation.id} detail={detail} review={detail.review} />;
  const editorialStage = ["editor_recommendation", "chief_decision", "revision_assessment"].includes(detail.stage);
  const formalRevision = detail.editorial?.mode === "author" && !!detail.editorial.revision_request;
  return <><header className={styles.recordHeader}><div><span>{detail.number}</span><span className={styles.status}>{detail.stage_label}</span></div><h1>{detail.title || "未命名投稿"}</h1><p>{detail.version ? `第 ${detail.version.version_no} 版` : "暂无版本"} · 修订 {detail.revision}{detail.version?.frozen_at ? " · 已冻结" : ""}</p></header>{detail.editorial?.mode === "author" && <EditorialFeedback detail={detail} />}{detail.return_request && !formalRevision && <section className={styles.panel}><div className={styles.notice}><strong>退回作者修改</strong><p className={styles.preserve}>{detail.return_request.reason}</p><p>重新提交后返回：{stageLabels[detail.return_request.return_to] ?? detail.return_request.return_to}</p></div></section>}{detail.is_legacy ? <section className={styles.panel}><p className={styles.notice}>这是旧版原型的只读记录，历史资料不完整，不能据此认定已经通过审核。</p>{detail.version && <Snapshot version={detail.version} legacy />}</section> : detail.can_edit_intake && detail.version ? <IntakeForm detail={detail} /> : <section className={styles.panel}>{detail.own_tasks.length > 0 && <div className={styles.notice}>{detail.own_tasks.map(task => <p key={task.id}>{task.label}{task.status === "waiting" ? " · 等待中" : " · 需要你处理"}</p>)}</div>}{detail.editorial?.mode === "staff" && <EditorialActions key={`${detail.stage}:${detail.version?.id ?? detail.current_version_id}`} detail={detail} editorial={detail.editorial} />}{detail.review?.mode === "staff" && !editorialStage && <StaffPeerReview key={detail.review.round?.id ?? "new-round"} detail={detail} review={detail.review} />}{detail.allowed_actions.length > 0 && <ActionPanel detail={detail} />}{detail.version ? <Snapshot version={detail.version} /> : <p>当前没有对你开放的稿件版本。</p>}</section>}<section className={styles.panel}><h2>进展</h2>{detail.timeline.length ? <ol className={styles.timeline}>{detail.timeline.map(step => <li key={step.id}><strong>{step.label}</strong><span>{step.status === "completed" ? "已完成" : step.status === "active" ? "进行中" : step.status}{step.cycle > 1 ? ` · 第${step.cycle}轮` : ""}</span>{step.completed_at && <time>{dateText(step.completed_at)}</time>}</li>)}</ol> : <p className={styles.subtle}>尚无流程记录。</p>}</section></>;
}

function IntakeForm({ detail }: { detail: Detail }) {
  const { mutate, refresh, setUnsaved } = usePublishing();
  const [data, setData] = useState<IntakeData>(() => structuredClone(detail.version!.data));
  const [baseRevision, setBaseRevision] = useState(detail.revision); const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState(""); const [error, setError] = useState("");
  const [uploadPurpose, setUploadPurpose] = useState("manuscript"); const [file, setFile] = useState<File | null>(null);
  const [conflict, setConflict] = useState(false); const [pending, setPending] = useState<{ kind: "save" | "upload"; data: object } | null>(null);
  const errorRef = useRef<HTMLDivElement>(null); const uploadInput = useRef<HTMLInputElement>(null);
  const serverChanged = detail.revision !== baseRevision;
  useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
  useEffect(() => { if (!dirty) return; function warn(event: BeforeUnloadEvent) { event.preventDefault(); } window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  if (!dirty && !busy && detail.revision !== baseRevision && detail.version) { setData(structuredClone(detail.version.data)); setBaseRevision(detail.revision); }
  function update<K extends keyof IntakeData>(key: K, value: IntakeData[K]) { setData(previous => ({ ...previous, [key]: value })); setDirty(true); setPending(null); setNotice(""); }
  function author(index: number, patch: Partial<Author>) { update("authors", data.authors.map((item, position) => position === index ? { ...item, ...patch } : item)); }
  function declaration<K extends keyof IntakeData["declarations"]>(key: K, value: IntakeData["declarations"][K]) { update("declarations", { ...data.declarations, [key]: value }); }
  function fail(failure: unknown) { setError((failure as Error).message); if (failure instanceof APIError && failure.status === 409) setConflict(true); requestAnimationFrame(() => errorRef.current?.focus()); }
  async function save(retryData?: object) {
    const payload = retryData ?? { expected_revision: baseRevision, data };
    setBusy(true); setError(""); setNotice(""); setPending({ kind: "save", data: payload });
    try { const result = await mutate<{ revision: number }>(`/manuscripts/${detail.id}/intake`, payload, "PATCH"); setBaseRevision(result.revision); setDirty(false); setUnsaved(false); setPending(null); setConflict(false); setNotice("资料已保存。"); await refresh(); }
    catch (failure) { fail(failure); } finally { setBusy(false); }
  }
  async function upload(retryData?: object) {
    setBusy(true); setError(""); setNotice("");
    try {
      let payload = retryData;
      if (!payload) {
        if (!file) throw new Error("请先选择 TXT 或 Markdown 文件。");
        if (!/\.(txt|md)$/i.test(file.name) || file.size < 1 || file.size > 1048576) throw new Error("仅支持 1 字节至 1 MiB 的 TXT 或 Markdown 文件。");
        const bytes = new Uint8Array(await file.arrayBuffer());
        try { new TextDecoder("utf-8", { fatal: true }).decode(bytes); } catch { throw new Error("文件不是有效 UTF-8 文本，请重新导出后上传。"); }
        let binary = ""; for (let start = 0; start < bytes.length; start += 8192) binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
        payload = { expected_revision: baseRevision, file: { filename: file.name, content_base64: btoa(binary), purpose: uploadPurpose } };
      }
      setPending({ kind: "upload", data: payload });
      const result = await mutate<{ revision: number }>(`/manuscripts/${detail.id}/files`, payload);
      setBaseRevision(result.revision); setPending(null); setFile(null); if (uploadInput.current) uploadInput.current.value = ""; setNotice("文件已上传并校验保存。"); await refresh();
    } catch (failure) { fail(failure); } finally { setBusy(false); }
  }
  async function reloadLatest() { if (dirty && !window.confirm("放弃当前未保存修改，并载入服务器上的最新资料？")) return; setDirty(false); setUnsaved(false); setConflict(false); setPending(null); setError(""); if (detail.version) setData(structuredClone(detail.version.data)); setBaseRevision(detail.revision); await refresh(); }
  const disabled = busy || conflict || serverChanged;
  return <section className={styles.panel}>
    {(conflict || serverChanged) && <div role="alert" className={styles.notice}>稿件已发生变化。当前修改仍保留；请复制需要保留的内容，再重新载入。<button onClick={() => void reloadLatest()} disabled={busy}>载入最新资料</button></div>}
    {error && <div ref={errorRef} tabIndex={-1} role="alert" className={styles.error}>{error}{pending && !conflict && <button onClick={() => pending.kind === "save" ? void save(pending.data) : void upload(pending.data)} disabled={busy}>重试上次操作</button>}</div>}
    <div aria-live="polite" className={styles.saved}>{notice || (dirty ? "有未保存的修改" : "")}</div>
    <form onSubmit={event => { event.preventDefault(); void save(); }} noValidate>
      <fieldset disabled={busy} className={styles.fields}><legend>投稿资料</legend>
        <label htmlFor="intake-title">标题<input id="intake-title" name="title" autoComplete="off" maxLength={500} value={data.title} onChange={event => update("title", event.target.value)} /></label>
        <div className={styles.fieldControl}><label htmlFor="intake-abstract">摘要</label><textarea id="intake-abstract" name="abstract" autoComplete="off" rows={7} maxLength={12000} value={data.abstract} onChange={event => update("abstract", event.target.value)} /></div>
        <div className={styles.fieldRow}><div className={styles.fieldControl}><label htmlFor="intake-language">稿件语言</label><select id="intake-language" name="language" value={data.language} onChange={event => update("language", event.target.value as "zh" | "en")}><option value="zh">中文</option><option value="en">英文</option></select></div><label>文章类型<input readOnly value="研究论文" aria-label="文章类型" /></label></div>
        <div className={styles.fieldControl}><label htmlFor="intake-keywords">关键词 · 每行一个</label><textarea id="intake-keywords" name="keywords" autoComplete="off" rows={3} value={data.keywords.join("\n")} onChange={event => update("keywords", event.target.value.split("\n"))} /></div>
      </fieldset>
      <fieldset disabled={busy} className={styles.fields}><legend>作者与署名顺序</legend>{data.authors.map((item, index) => <div className={styles.author} key={index}><div className={styles.authorHeading}><h3>作者 {index + 1}</h3><div><button type="button" disabled={index === 0} aria-label={`将作者${index + 1}前移`} onClick={() => { const authors = [...data.authors]; [authors[index - 1], authors[index]] = [authors[index], authors[index - 1]]; update("authors", authors); }}>前移</button><button type="button" disabled={index === data.authors.length - 1} aria-label={`将作者${index + 1}后移`} onClick={() => { const authors = [...data.authors]; [authors[index + 1], authors[index]] = [authors[index], authors[index + 1]]; update("authors", authors); }}>后移</button><button type="button" aria-label={`移除作者${index + 1}`} onClick={() => update("authors", data.authors.filter((_, position) => position !== index))}>移除</button></div></div><div className={styles.fieldRow}><label htmlFor={`author-${index}-name`}>姓名<input id={`author-${index}-name`} name={`authors.${index}.name`} autoComplete="off" maxLength={200} value={item.name} onChange={event => author(index, { name: event.target.value })} /></label><label htmlFor={`author-${index}-email`}>邮箱<input id={`author-${index}-email`} name={`authors.${index}.email`} type="email" spellCheck={false} autoComplete="off" maxLength={254} value={item.email} onChange={event => author(index, { email: event.target.value })} /></label></div><label htmlFor={`author-${index}-orcid`}>ORCID · 仅检查格式<input id={`author-${index}-orcid`} name={`authors.${index}.orcid`} autoComplete="off" spellCheck={false} maxLength={64} value={item.orcid ?? ""} onChange={event => author(index, { orcid: event.target.value || null })} /></label><div className={styles.fieldControl}><label htmlFor={`author-${index}-affiliations`}>单位 · 每行一个</label><textarea id={`author-${index}-affiliations`} name={`authors.${index}.affiliations`} autoComplete="off" rows={2} value={item.affiliations.join("\n")} onChange={event => author(index, { affiliations: event.target.value.split("\n") })} /></div><div className={styles.fieldControl}><label htmlFor={`author-${index}-contributions`}>贡献 · 每行一项</label><textarea id={`author-${index}-contributions`} name={`authors.${index}.contributions`} autoComplete="off" rows={2} value={item.contributions.join("\n")} onChange={event => author(index, { contributions: event.target.value.split("\n") })} /></div><label className={styles.checkbox}><input type="checkbox" name={`authors.${index}.corresponding`} checked={item.corresponding} onChange={event => author(index, { corresponding: event.target.checked })} />通讯作者</label></div>)}<button type="button" disabled={data.authors.length >= 20} onClick={() => update("authors", [...data.authors, newAuthor()])}>添加作者</button></fieldset>
      <fieldset disabled={busy} className={styles.fields}><legend>基金与声明</legend><div className={styles.fieldControl}><label htmlFor="funding-statement">基金资助说明</label><textarea id="funding-statement" name="funding_statement" autoComplete="off" rows={3} maxLength={4000} value={data.funding_statement} onChange={event => update("funding_statement", event.target.value)} /></div><label className={styles.checkbox}><input id="declaration-originality" name="originality" type="checkbox" checked={data.declarations.originality} onChange={event => declaration("originality", event.target.checked)} />我确认稿件为原创，未一稿多投</label><label className={styles.checkbox}><input id="declaration-copyright" name="copyright" type="checkbox" checked={data.declarations.copyright} onChange={event => declaration("copyright", event.target.checked)} />我确认拥有投稿所需的版权或授权</label><div className={styles.fieldControl}><label htmlFor="declaration-coi">利益冲突</label><select id="declaration-coi" name="competing_interests" value={data.declarations.competing_interests} onChange={event => declaration("competing_interests", event.target.value as IntakeData["declarations"]["competing_interests"])}><option value="unanswered">请由作者本人选择</option><option value="none">无利益冲突</option><option value="declared">存在利益冲突，需说明</option></select></div>{data.declarations.competing_interests === "declared" && <div className={styles.fieldControl}><label htmlFor="declaration-coi-text">利益冲突说明</label><textarea id="declaration-coi-text" name="competing_interests_text" autoComplete="off" rows={3} maxLength={4000} value={data.declarations.competing_interests_text} onChange={event => declaration("competing_interests_text", event.target.value)} /></div>}<div className={styles.fieldControl}><label htmlFor="declaration-ethics">伦理审批适用性</label><select id="declaration-ethics" name="ethics" value={data.declarations.ethics} onChange={event => declaration("ethics", event.target.value as IntakeData["declarations"]["ethics"])}><option value="unanswered">请由作者本人选择</option><option value="not_applicable">不适用</option><option value="approved">已取得伦理批准</option></select></div>{data.declarations.ethics === "approved" && <label htmlFor="declaration-ethics-reference">伦理批准机构或编号<input id="declaration-ethics-reference" name="ethics_reference" autoComplete="off" maxLength={1000} value={data.declarations.ethics_reference} onChange={event => declaration("ethics_reference", event.target.value)} /></label>}</fieldset>
      <div className={styles.formActions}><button className={styles.primary} type="submit" disabled={disabled}>{busy && pending?.kind === "save" ? "正在保存…" : "保存资料"}</button></div>
    </form>
    <section className={styles.section}><h2>稿件文件</h2><p className={styles.subtle}>UTF-8 编码的 TXT / Markdown，单个不超过 1 MiB。仅检查文本与完整性，未执行病毒扫描。</p><Files files={detail.version?.files ?? []} /><div className={styles.fields}><div className={styles.fieldControl}><label htmlFor="upload-purpose">文件用途</label><select id="upload-purpose" name="file_purpose" value={uploadPurpose} onChange={event => setUploadPurpose(event.target.value)} disabled={busy}><option value="manuscript">完整稿件</option><option value="blinded_manuscript">匿名稿件</option><option value="response">修回说明</option></select></div><label htmlFor="manuscript-upload">选择文件<input ref={uploadInput} id="manuscript-upload" type="file" accept=".txt,.md,text/plain,text/markdown" disabled={busy} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label><button onClick={() => void upload()} disabled={disabled || dirty || !file}>{busy && pending?.kind === "upload" ? "正在上传…" : "上传并保存"}</button>{dirty && <p className={styles.subtle}>请先保存资料，再上传文件或准备审核。</p>}</div></section>
    <section className={styles.section}><h2>待补资料</h2>{detail.missing.length ? <ul className={styles.missing}>{detail.missing.map(item => <li key={item.field}>{item.message}</li>)}</ul> : <p>已满足当前投稿资料要求。</p>}{dirty && <p className={styles.subtle}>清单基于已保存资料；保存后更新。</p>}</section>
    {Object.keys(detail.field_sources).length > 0 && <details className={styles.section}><summary>字段来源</summary><pre className={styles.json}>{JSON.stringify(detail.field_sources, null, 2)}</pre></details>}
    <ActionPanel detail={detail} disabled={dirty || busy || conflict || serverChanged} />
  </section>;
}

function ActionPanel({ detail, disabled = false }: { detail: Detail; disabled?: boolean }) {
  if (detail.staff_review && detail.allowed_actions.some(action => action.action === "record_check" || action.action === "assign_editor")) return <StageActions key={`${detail.id}:${detail.stage}`} detail={detail} />;
  return <SubmitActions detail={detail} disabled={disabled} />;
}

function SubmitActions({ detail, disabled = false }: { detail: Detail; disabled?: boolean }) {
  const { mutate, refresh } = usePublishing(); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [url, setURL] = useState<string | null>(null);
  async function prepare(action: string) { setBusy(true); setError(""); try { const result = await mutate<{ proposal_id: string }>(`/manuscripts/${detail.id}/proposals`, { expected_revision: detail.revision, action_type: action, data: {} }); setURL(`/publishing/review/${result.proposal_id}`); } catch (failure) { setError((failure as Error).message); await refresh(); } finally { setBusy(false); } }
  const actions = detail.allowed_actions.filter(action => action.action === "submit" || action.action === "submit_revision");
  if (!actions.length) return null;
  return <section className={styles.section}><h2>下一步</h2>{error && <p role="alert" className={styles.error}>{error}</p>}{actions.map(action => <button key={action.action} disabled={disabled || busy} onClick={() => void prepare(action.action)}>{busy ? "正在准备…" : action.label}</button>)}{url && <p role="status"><Link className={styles.actionLink} aria-disabled={disabled} onClick={event => { if (disabled) event.preventDefault(); }} href={url}>打开完整资料并由负责人确认</Link></p>}</section>;
}

export function Files({ files }: { files: VersionFile[] }) {
  return files.length ? <ul className={styles.files}>{files.map(file => <li key={file.id}><div><strong>{purposeLabels[file.purpose] ?? file.purpose}</strong>{fileURL(file) ? <a href={fileURL(file)} download>{file.name}</a> : <span>{file.name}</span>}</div><small>{new Intl.NumberFormat("zh-CN").format(file.byte_size)} 字节 · {file.media_type} · {file.visibility}</small><code>SHA-256 {file.sha256}</code><small>检查：{file.check_method} · 扫描状态：{file.scan_status}</small></li>)}</ul> : <p className={styles.subtle}>尚未上传文件。</p>;
}

export function Snapshot({ version, legacy = false, reviewSnapshot = false }: { version: Version; legacy?: boolean; reviewSnapshot?: boolean }) {
  const data = version.data;
  return <div className={styles.snapshot}><dl><dt>标题</dt><dd>{data.title || "未填写"}</dd><dt>摘要</dt><dd className={styles.preserve}>{data.abstract || "未填写"}</dd><dt>语言与类型</dt><dd>{data.language === "zh" ? "中文" : data.language === "en" ? "英文" : "未记录"} · {data.article_type === "research_article" ? "研究论文" : data.article_type || "未记录"}</dd><dt>关键词</dt><dd>{data.keywords?.filter(Boolean).join("、") || "未填写"}</dd><dt>作者（署名顺序）</dt><dd><ol className={styles.snapshotAuthors}>{data.authors?.map((item, index) => <li key={index}><strong>{item.name || "姓名未填写"}{item.corresponding ? "（通讯作者）" : ""}</strong><span>{item.email || "邮箱未填写"}</span>{item.orcid && <span>ORCID {item.orcid} · 格式信息，未核实身份</span>}<span>单位：{item.affiliations?.filter(Boolean).join("；") || "未填写"}</span><span>贡献：{item.contributions?.filter(Boolean).join("；") || "未填写"}</span></li>)}</ol></dd><dt>基金资助</dt><dd className={styles.preserve}>{data.funding_statement || "未填写"}</dd></dl>{!legacy && data.declarations && <><h2>作者声明</h2><dl><dt>原创性</dt><dd>{data.declarations.originality ? "作者已确认" : "未确认"}</dd><dt>版权与授权</dt><dd>{data.declarations.copyright ? "作者已确认" : "未确认"}</dd><dt>利益冲突</dt><dd>{({ unanswered: "未回答", none: "无利益冲突", declared: "已声明利益冲突" })[data.declarations.competing_interests]}{data.declarations.competing_interests_text && <p className={styles.preserve}>{data.declarations.competing_interests_text}</p>}</dd><dt>伦理审批</dt><dd>{({ unanswered: "未回答", not_applicable: "不适用", approved: "已批准" })[data.declarations.ethics]}{data.declarations.ethics_reference && <p>{data.declarations.ethics_reference}</p>}</dd></dl></>}<h2>文件与内容指纹</h2><Files files={version.files} /><p className={styles.subtle}>第 {version.version_no} 版 · {version.frozen_at ? `冻结于 ${dateText(version.frozen_at)}` : reviewSnapshot ? "审核准备时的版本快照" : "草稿尚未冻结"}</p></div>;
}
