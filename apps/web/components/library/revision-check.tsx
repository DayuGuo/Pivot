"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { requestId, sha256Bytes } from "../browser";
import { fileDownloadURL, LibraryError, readJSON, requireLibrarySession } from "./api";
import type { Dossier, Page, Session } from "./types";
import { editorLabels, findingLabels, implementationLabels, materialLabels, responseLabels, uuid, validPacket, validReview, type RevisionCitation, type RevisionHistoryItem, type RevisionPacket, type RevisionReview } from "./revision-types";
import styles from "./library.module.css";
import local from "./revision-check.module.css";

type Props = { detail: Dossier; session: Session; checkId?: string; onDirty: (dirty: boolean) => void; onDenied: () => void };
type Security = { here: () => boolean; read: <T>(path: string) => Promise<T>; authorize: () => Promise<void>; failed: (error: unknown) => void; session: Session; dirty: (key: string, value: boolean) => void };
type Version = Dossier["versions"][number];
type ReviewPage = { items: RevisionReview[]; next_cursor: number | null };

function downloadJSON(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function RevisionCheck(props: Props) {
  const key = `${props.detail.id}:${props.detail.version_id}:${props.detail.revision}:${props.session.user.id}:${props.session.journal.id}:${props.session.user.role}:${props.session.csrf_token}:${props.checkId ?? "new"}`;
  return <RevisionPanel key={key} {...props} />;
}

function RevisionPanel({ detail, session, checkId, onDirty, onDenied }: Props) {
  const router = useRouter();
  const root = `/api/dossiers/${detail.id}/revision-checks`;
  const [packet, setPacket] = useState<RevisionPacket | null>(null), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [notice, setNotice] = useState("");
  const [versions, setVersions] = useState<Version[]>(detail.versions), [versionCursor, setVersionCursor] = useState(detail.versions_next_cursor);
  const [history, setHistory] = useState<RevisionHistoryItem[]>([]), [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [base, setBase] = useState("");
  const [requirements, setRequirements] = useState([{ text: "", original_context: "" }]);
  const [response, setResponse] = useState(""), [sourceNote, setSourceNote] = useState("");
  const [complete, setComplete] = useState({ base_complete: false, revised_complete: false, requirements_complete: false, response_complete: false });
  const [authorized, setAuthorized] = useState(false);
  const [initialSession] = useState(session);
  const alive = useRef(true), lock = useRef(false), uri = useRef("");
  const callbacks = useRef({ onDirty, onDenied });
  useEffect(() => { callbacks.current = { onDirty, onDenied }; }, [onDirty, onDenied]);
  const changes = useRef(new Set<string>());
  const pending = useRef<{ key: string; id: string; checkId?: string } | null>(null);
  const [recoverRead, setRecoverRead] = useState(false);
  function here() { return alive.current && uri.current === window.location.pathname + window.location.search; }
  function dirty(key: string, value: boolean) { if (value) changes.current.add(key); else changes.current.delete(key); callbacks.current.onDirty(changes.current.size > 0); }
  function failed(failure: unknown) {
    if (!here() || (failure instanceof DOMException && failure.name === "AbortError")) return;
    if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { setPacket(null); setHistory([]); callbacks.current.onDenied(); return; }
    setError((failure as Error).message || "核对未完成，请重试。");
  }
  async function authorize() { await requireLibrarySession(session); if (!here()) throw new DOMException("页面已切换", "AbortError"); }
  async function read<T>(path: string): Promise<T> {
    await authorize(); const value = await readJSON<T>(path); await authorize(); return value;
  }
  const security: Security = { here, read, authorize, failed, session, dirty };
  useEffect(() => {
    alive.current = true; uri.current = window.location.pathname + window.location.search;
    const active = () => alive.current && uri.current === window.location.pathname + window.location.search;
    void (async () => {
      try {
        await requireLibrarySession(initialSession); if (!active()) return;
        if (checkId) {
          const value = await readJSON<RevisionPacket>(`${root}/${checkId}`);
          await requireLibrarySession(initialSession); if (!active()) return;
          if (!validPacket(value, detail.id, checkId)) throw new LibraryError(502, "核对包未完整收到，请重新载入。");
          setPacket(value);
        }
        const page = await readJSON<Page<RevisionHistoryItem>>(root);
        await requireLibrarySession(initialSession); if (!active()) return;
        if (!Array.isArray(page.items)) throw new LibraryError(502, "历史列表未完整收到，请重新载入。");
        setHistory(page.items); setHistoryCursor(page.next_cursor ?? null);
      } catch (failure) {
        if (!active()) return;
        if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { setPacket(null); callbacks.current.onDenied(); }
        else setError((failure as Error).message);
      }
    })();
    return () => { alive.current = false; callbacks.current.onDirty(false); };
  }, [root, checkId, detail.id, initialSession]);
  function changed() { pending.current = null; setRecoverRead(false); setNotice(""); dirty("create", true); }
  async function create(event: FormEvent) {
    event.preventDefault(); if (lock.current || !authorized || !base) return;
    lock.current = true; setBusy(true); setError("");
    const body = { expected_revision: detail.revision, base_version_id: base, revised_version_id: detail.version_id, requirements, response_text: response, source_note: sourceNote, ...complete, authorized_material: true };
    const encoded = JSON.stringify(body);
    if (pending.current?.key !== encoded) pending.current = { key: encoded, id: requestId() };
    try {
      await authorize();
      if (!pending.current.checkId) {
        const result = await readJSON<{ dossier_id: string; check_id: string }>(root, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ ...body, request_id: pending.current.id }) });
        if (!here()) return;
        if (result.dossier_id !== detail.id || !uuid(result.check_id)) throw new LibraryError(502, "未完整收到回执；保持材料不变，重试恢复同一请求。");
        pending.current.checkId = result.check_id; setRecoverRead(true);
      }
      const value = await read<RevisionPacket>(`${root}/${pending.current.checkId}`);
      if (!validPacket(value, detail.id, pending.current.checkId)) throw new LibraryError(502, "核对包未完整收到，请重试读取已生成的核对包。");
      setPacket(value); dirty("create", false); setNotice("核对包已生成；人工判断与出版决定分开保存。");
      router.push(`/library?dossier=${detail.id}&panel=revisions&revision_check=${value.id}`);
    } catch (failure) { failed(failure); } finally { lock.current = false; if (here()) setBusy(false); }
  }
  async function more(kind: "versions" | "history") {
    if (lock.current) return; lock.current = true; setBusy(true); setError("");
    try {
      if (kind === "versions") {
        const next = await read<Page<Version>>(`/api/dossiers/${detail.id}/versions?cursor=${encodeURIComponent(versionCursor ?? "")}`);
        if (!Array.isArray(next.items)) throw new LibraryError(502, "版本列表未完整收到，请重试。");
        setVersions(old => [...old, ...next.items.filter(v => !old.some(o => o.id === v.id))]); setVersionCursor(next.next_cursor);
      } else {
        const next = await read<Page<RevisionHistoryItem>>(`${root}?cursor=${encodeURIComponent(historyCursor ?? "")}`);
        if (!Array.isArray(next.items)) throw new LibraryError(502, "历史列表未完整收到，请重试。");
        setHistory(old => [...old, ...next.items.filter(v => !old.some(o => o.id === v.id))]); setHistoryCursor(next.next_cursor ?? null);
      }
    } catch (failure) { failed(failure); } finally { lock.current = false; if (here()) setBusy(false); }
  }
  async function exportPacket() {
    if (!packet || lock.current) return; lock.current = true; setBusy(true); setError("");
    try {
      const value = await read<RevisionPacket>(`${root}/${packet.id}/export`);
      if (!validPacket(value, detail.id, packet.id) || value.digest !== packet.digest) throw new LibraryError(409, "导出与当前核对包不符，请重新载入。");
      downloadJSON(value, `pivot-revision-${packet.id}.json`);
    } catch (failure) { failed(failure); } finally { lock.current = false; if (here()) setBusy(false); }
  }
  async function reloadPacket() {
    if (!checkId || lock.current) return; lock.current = true; setBusy(true); setError("");
    try {
      const value = await read<RevisionPacket>(`${root}/${checkId}`);
      if (!validPacket(value, detail.id, checkId)) throw new LibraryError(502, "核对包未完整收到，请重新读取。");
      setPacket(value);
    } catch (failure) { failed(failure); } finally { lock.current = false; if (here()) setBusy(false); }
  }
  return <><div className={styles.materialHeader}><h2>修回核对</h2><Link href={`/library?dossier=${detail.id}`}>返回资料</Link></div>
    <div className={local.body} aria-label="内部修回核对">
      {error && <p role="alert">{error}</p>}{error && checkId && <button type="button" disabled={busy} onClick={() => void reloadPacket()}>重新读取核对包</button>}{notice && <p role="status">{notice}</p>}
      {!checkId && !packet && <form onSubmit={event => void create(event)}>
        <p>比较已保存的两个版本。请先将复合意见拆成可单独核对的要求；保留原意见上下文。</p>
        <fieldset disabled={busy}>
          <label>原稿版本<select name="revision-base" value={base} required onChange={e => { setBase(e.target.value); changed(); }}><option value="">选择较早版本</option>{versions.filter(v => v.number < detail.version_no).map(v => <option key={v.id} value={v.id}>v{v.number} · {v.title}</option>)}</select></label>
          {versionCursor && <button type="button" onClick={() => void more("versions")}>加载更早版本</button>}
          <p className={local.muted}>修订稿：v{detail.version_no} · {detail.data.title}</p>
          {requirements.map((item, index) => <div className={local.requirement} key={index}><label>核对要求 {index + 1}<textarea name={`requirement-${index}`} required maxLength={1200} value={item.text} onChange={e => { setRequirements(old => old.map((v, i) => i === index ? { ...v, text: e.target.value } : v)); changed(); }} /></label><label>原意见上下文 {index + 1}<textarea name={`requirement-context-${index}`} required maxLength={4000} value={item.original_context} onChange={e => { setRequirements(old => old.map((v, i) => i === index ? { ...v, original_context: e.target.value } : v)); changed(); }} /></label>{requirements.length > 1 && <button type="button" onClick={() => { setRequirements(old => old.filter((_, i) => i !== index)); changed(); }}>移除要求 {index + 1}</button>}</div>)}
          {requirements.length < 8 && <button type="button" onClick={() => { setRequirements(old => [...old, { text: "", original_context: "" }]); changed(); }}>添加核对要求</button>}
          <label>作者逐点回复<textarea name="revision-response" required maxLength={24000} value={response} onChange={e => { setResponse(e.target.value); changed(); }} /></label>
          <label>材料来源与缺口<textarea name="revision-source-note" required minLength={5} maxLength={2000} value={sourceNote} onChange={e => { setSourceNote(e.target.value); changed(); }} /></label>
          <p className={local.muted}>完整度如实填写；只有节选时保留未勾选，仍可核对有依据的项目。</p>
          {([ ["base_complete", "原稿正文完整"], ["revised_complete", "修订稿正文完整"], ["requirements_complete", "已包含全部需要核对的意见"], ["response_complete", "作者回复完整"] ] as const).map(([key, label]) => <label className={local.check} key={key}><input type="checkbox" name={key} checked={complete[key]} onChange={e => { setComplete(old => ({ ...old, [key]: e.target.checked })); changed(); }} />{label}</label>)}
          <label className={local.check}><input type="checkbox" name="revision-authorized" checked={authorized} onChange={e => { setAuthorized(e.target.checked); changed(); }} />我确认这些材料为合成或已获授权的非保密资料，可用于本次模型核对。</label>
        </fieldset>
        <button className={styles.primary} disabled={busy || !authorized || !base}>{busy ? "正在核对…" : recoverRead ? "恢复已生成核对包" : "生成修回核对"}</button>
      </form>}
      {checkId && !packet && !error && <p role="status">正在载入核对包…</p>}
      {packet && <section>
        <div className={local.actions}><h3>v{packet.base_version_no} 与 v{packet.revised_version_no}</h3><button type="button" disabled={busy} onClick={() => void exportPacket()}>导出修回核对 JSON</button></div>
        <p>{packet.report.provider === "mock" ? "Mock 模拟：未运行语义判断。" : "DeepSeek 辅助核对：结论须由本人查证。"}</p>
        {!packet.is_current && <p className={styles.warning}>这是历史版本的核对包，判断不会自动迁移到当前稿件。</p>}
        <p className={local.muted}>人工判断不代表正式修回决定、录用或拒稿。</p>
        <div className={local.actions}><Link href={`/library/review/${packet.base_version_id}?dossier=${detail.id}`}>查看原稿 v{packet.base_version_no}</Link><Link href={`/library/review/${packet.revised_version_id}?dossier=${detail.id}`}>查看修订稿 v{packet.revised_version_no}</Link></div>
        <details><summary>材料与读取范围</summary><p>{packet.materials.source_note}</p>{Object.entries(packet.report.coverage).map(([kind, c]) => <p key={kind}>{materialLabels[kind as keyof typeof materialLabels]}：本次读取 {c.read_characters}/{c.total_characters} 字符；{c.source_complete ? "所提供材料标为完整" : "所提供材料不完整或尚未确认完整"}</p>)}<pre>{packet.materials.response_text}</pre></details>
        {packet.report.rows.map(row => <article className={local.point} key={row.point_id} aria-label={`核对项 ${row.point_id}`}><h3>{row.point_id} · {row.point.text}</h3><details><summary>原意见上下文</summary><blockquote>{row.point.original_context}</blockquote></details><p>{findingLabels[row.status] ?? "待核对"}：{row.reason}</p><div className={local.sources}>{row.citations.map((citation, index) => <CitationSource key={index} citation={citation} packet={packet} dossierId={detail.id} security={security} />)}</div><PointReview pointId={row.point_id} packet={packet} security={security} /></article>)}
      </section>}
      <section><h3>已保存的核对包</h3>{history.length ? <ul className={local.history}>{history.map(item => <li key={item.id}><Link href={`/library?dossier=${detail.id}&panel=revisions&revision_check=${item.id}`}>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))} · {item.point_count} 项 · {item.provider === "mock" ? "Mock 模拟" : "DeepSeek"}{item.is_current ? "" : " · 历史版本"}</Link></li>)}</ul> : <p className={local.muted}>尚无已保存的核对包。</p>}{historyCursor && <button type="button" disabled={busy} onClick={() => void more("history")}>加载更早核对包</button>}</section>
    </div></>;
}

function PointReview({ pointId, packet, security }: { pointId: string; packet: RevisionPacket; security: Security }) {
  const incoming = packet.reviews[pointId] ?? null;
  const [latest, setLatest] = useState(incoming);
  const [seenHead, setSeenHead] = useState(incoming?.id ?? null);
  const [history, setHistory] = useState<RevisionReview[]>([]), [cursor, setCursor] = useState<number | null>(null);
  const [response, setResponse] = useState(""), [implementation, setImplementation] = useState(""), [editor, setEditor] = useState("");
  const [reason, setReason] = useState(""), [ack, setAck] = useState(false), [busy, setBusy] = useState(false), [notice, setNotice] = useState("");
  const [recoverRead, setRecoverRead] = useState(false);
  const lock = useRef(false), pending = useRef<{ key: string; id: string; expectedReviewId: string | null; saved?: RevisionReview } | null>(null);
  const url = `/api/dossiers/${packet.dossier_id}/revision-checks/${packet.id}/points/${pointId}/reviews`;
  // Adjust only head-dependent state when a parent reread supplies a new head.
  // Keep the person's three choices and reason; never recreate the form or
  // discard an unknown write's request/head. A delayed older read cannot roll
  // back a newer head already obtained from a completed local write/history.
  if (seenHead !== (incoming?.id ?? null)) {
    setSeenHead(incoming?.id ?? null);
    if (incoming && (!latest || incoming.review_no >= latest.review_no)) {
      setLatest(incoming); setAck(false);
    }
  }
  function changed() { setAck(false); setNotice(""); setRecoverRead(false); pending.current = null; security.dirty(pointId, true); }
  async function load(before?: number) {
    const page = await security.read<ReviewPage>(url + (before ? `?before=${before}` : ""));
    if (!Array.isArray(page.items) || !page.items.every(item => validReview(item, pointId))) throw new LibraryError(502, "人工判断历史未完整收到，请重试读取。");
    setHistory(old => before ? [...old, ...page.items] : page.items); setCursor(page.next_cursor);
    if (!before) setLatest(page.items[0] ?? null);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (lock.current || !ack) return;
    lock.current = true; setBusy(true); setNotice("");
    // Loading history after an unknown/known write must not silently rebase its
    // optimistic head or replace the original UUID with a second mutation.
    const expectedReviewId = pending.current ? pending.current.expectedReviewId : latest?.id ?? null;
    const body = { check_digest: packet.digest, expected_review_id: expectedReviewId, response_verdict: response, implementation_verdict: implementation, editor_verdict: editor, reason: reason.trim(), acknowledged: true };
    const encoded = JSON.stringify(body);
    if (pending.current?.key !== encoded) pending.current = { key: encoded, id: requestId(), expectedReviewId };
    let writing = false;
    try {
      await security.authorize();
      if (!pending.current.saved) {
        writing = true;
        const value = await readJSON<RevisionReview>(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": security.session.csrf_token }, body: JSON.stringify({ ...body, request_id: pending.current.id }) });
        if (!security.here()) return;
        if (!validReview(value, pointId) || value.reason !== body.reason || value.response_verdict !== response || value.implementation_verdict !== implementation || value.editor_verdict !== editor) throw new LibraryError(502, "未完整收到保存回执；保持判断不变，再次保存恢复同一请求。");
        pending.current.saved = value; writing = false; setRecoverRead(true);
      }
      await load(); if (!security.here()) return;
      setAck(false); setRecoverRead(false); security.dirty(pointId, false); pending.current = null; setNotice("人工判断已保存。");
    } catch (failure) {
      if (security.here() && writing && failure instanceof LibraryError && failure.status === 409) {
        // A rejected optimistic write is known not to have applied. After an
        // explicit reread the person may confirm the retained draft against the
        // new head. Network errors and known-success read failures retain it.
        pending.current = null; setRecoverRead(false); setAck(false);
      }
      security.failed(failure);
    } finally { lock.current = false; if (security.here()) setBusy(false); }
  }
  async function historyPage(before?: number) {
    if (lock.current) return; lock.current = true; setBusy(true);
    try { await load(before); if (!before && security.here()) setAck(false); } catch (failure) { security.failed(failure); } finally { lock.current = false; if (security.here()) setBusy(false); }
  }
  return <section aria-label={`人工判断 ${pointId}`}>
    {latest && <p>已保存判断：{responseLabels[latest.response_verdict]}；{implementationLabels[latest.implementation_verdict]}；{editorLabels[latest.editor_verdict]}。{latest.reason}</p>}
    <form onSubmit={e => void save(e)}><fieldset disabled={busy}>
      <label>作者回应<select name={`response-${pointId}`} value={response} required onChange={e => { setResponse(e.target.value); changed(); }}><option value="">请选择</option>{Object.entries(responseLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>正文落实<select name={`implementation-${pointId}`} value={implementation} required onChange={e => { setImplementation(e.target.value); changed(); }}><option value="">请选择</option>{Object.entries(implementationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>编辑处理<select name={`editor-${pointId}`} value={editor} required onChange={e => { setEditor(e.target.value); changed(); }}><option value="">请选择</option>{Object.entries(editorLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>本人核对理由<textarea name={`reason-${pointId}`} required minLength={5} maxLength={2000} value={reason} onChange={e => { setReason(e.target.value); changed(); }} /></label>
      <label className={local.check}><input type="checkbox" name={`review-ack-${pointId}`} checked={ack} onChange={e => { setAck(e.target.checked); security.dirty(pointId, true); }} />我已对照原文核对本条，确认上述人工判断。</label>
    </fieldset><button disabled={busy || !ack}>{busy ? "正在保存…" : recoverRead ? "恢复已保存判断" : "保存人工判断"}</button></form>
    {notice && <p role="status">{notice}</p>}
    <details><summary onClick={() => { if (!history.length) void historyPage(); }}>人工判断历史</summary><ul className={local.history}>{history.map(item => <li key={item.id}>第 {item.review_no} 次：{responseLabels[item.response_verdict]}；{implementationLabels[item.implementation_verdict]}；{editorLabels[item.editor_verdict]}。{item.reason}</li>)}</ul>{cursor && <button type="button" disabled={busy} onClick={() => void historyPage(cursor)}>加载更早人工判断</button>}</details>
  </section>;
}

function CitationSource({ citation, packet, dossierId, security }: { citation: RevisionCitation; packet: RevisionPacket; dossierId: string; security: Security }) {
  const [located, setLocated] = useState<{ before: string; quote: string; after: string; download: string | null; originalDownload: string | null } | null>(null), [busy, setBusy] = useState(false);
  const lock = useRef(false);
  async function locate() {
    if (lock.current) return; lock.current = true; setBusy(true);
    try {
      await security.authorize();
      let text: string, download: string | null = null, originalDownload: string | null = null;
      if (citation.kind === "response") {
        if (citation.version_id !== packet.revised_version_id || citation.file_id !== `pasted-response:${packet.id}`) throw new LibraryError(409, "回复引用与核对包不符。");
        text = packet.materials.response_text;
      } else {
        const version = citation.kind === "base" ? packet.base_version_id : packet.revised_version_id;
        const value = await security.read<Dossier>(`/api/dossiers/${dossierId}/versions/${version}`);
        if (citation.version_id !== version || value.id !== dossierId || value.version_id !== version || value.version_no !== citation.version_no || !value.file || value.file.sha256 !== citation.sha256) throw new LibraryError(409, "引用文件或版本不匹配，请重新载入核对包。");
        text = value.file.text; download = fileDownloadURL(value.file.download_url);
        if (citation.original) {
          const document = value.document;
          if (!document || document.sha256 !== citation.original.sha256 || document.download_url !== citation.original.download_url || !citation.original.locations.every(location => document.segments.some(segment => segment.kind === location.kind && segment.number === location.number && location.start >= segment.start && location.end <= segment.end && Array.from(segment.text).slice(location.start - segment.start, location.end - segment.start).join("") === location.quote))) throw new LibraryError(409, "原件位置与引用不符，已停止定位。");
          originalDownload = fileDownloadURL(document.download_url);
        }
      }
      const sha = await sha256Bytes(new TextEncoder().encode(text).buffer);
      const characters = Array.from(text);
      if (sha !== citation.sha256 || !Number.isSafeInteger(citation.start) || !Number.isSafeInteger(citation.end) || citation.start < 0 || citation.end <= citation.start || citation.end > characters.length || characters.slice(citation.start, citation.end).join("") !== citation.quote) throw new LibraryError(409, "引文与保存的原文摘要或位置不一致，已停止定位。");
      await security.authorize();
      setLocated({ before: characters.slice(Math.max(0, citation.start - 200), citation.start).join(""), quote: citation.quote, after: characters.slice(citation.end, citation.end + 200).join(""), download, originalDownload });
    } catch (failure) { security.failed(failure); } finally { lock.current = false; if (security.here()) setBusy(false); }
  }
  return <div><button type="button" disabled={busy} onClick={() => void locate()}>{busy ? "正在定位…" : `定位${materialLabels[citation.kind]}原文`} · v{citation.version_no}</button><blockquote>{citation.quote}</blockquote>
    {located && <div><pre aria-label={`${materialLabels[citation.kind]}原文定位`}>{located.before}<mark>{located.quote}</mark>{located.after}</pre>{citation.original && <p className={local.muted}>{citation.original.locations.map(l => l.kind === "pdf_page" ? `PDF 第 ${l.number} 页` : `Word 提取段 ${l.number}`).join("、")}</p>}<div className={local.actions}>{located.download && <a href={located.download} download>下载该版正文</a>}{located.originalDownload && <a href={located.originalDownload} download>下载该版原件</a>}</div><details><summary>原文 SHA-256</summary><code>{citation.sha256}</code></details></div>}
  </div>;
}
