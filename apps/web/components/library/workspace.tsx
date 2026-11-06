"use client";
import IdentityControl from "../identity/control";
import PersonalCalendar from "../calendar/personal-calendar";
import GlobalSearch from "../search/global-search";
import { warnBeforeUnload } from "../browser";
import { requestId as newRequestId } from "../browser";

import Link from "next/link";
import NextSteps from "../assistant/next-steps";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import Glyph from "../editorial/icons";
import { SettingsButton } from "../settings/panel";
import { dossierListURL, LibraryError, readJSON } from "./api";
import DossierEditor from "./editor";
import MetadataExport from "./metadata-export";
import RevisionCheck from "./revision-check";
import DocumentUpload from "./document-upload";
import ImportReview from "./import-review";
import ImportHistory from "./import-history";
import EvaluationReview from "./evaluation-review";
import DossierReview from "./review";
import { citationText, EvidencePanel, MessageTurn } from "./evidence";
import { OriginalText, VersionList } from "./viewers";
import type { Citation, DocumentImport, Dossier, DossierData, DossierItem, Message, Page, Session, Upload } from "./types";
import styles from "./library.module.css";

export default function LibraryWorkspace({ reviewVersionId, importId, evaluationId }: { reviewVersionId?: string; importId?: string; evaluationId?: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const selectedId = search.get("dossier");
  const revisionPanel = search.get("panel") === "revisions";
  const revisionCheckId = search.get("revision_check") ?? undefined;
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<DossierItem[]>([]);
  const [detail, setDetail] = useState<Dossier | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [newDossier, setNewDossier] = useState(false);
  const [documentImport, setDocumentImport] = useState<DocumentImport | null>(null);
  const [uploadingDocument, setUploadingDocument] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState<"metadata" | "text" | "versions">("metadata");
  const [question, setQuestion] = useState("");
  const [query, setQuery] = useState("");
  const [dirty, setDirty] = useState(false);
  const [sourcePreview, setSourcePreview] = useState<{ snapshot: Dossier; citation: Citation } | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [locating, setLocating] = useState<string | null>(null);
  const citationRequest = useRef(0);
  const citationTrigger = useRef<HTMLButtonElement | null>(null);
  const [retryLabel, setRetryLabel] = useState("重试原请求");
  const [listCursor, setListCursor] = useState<string | null>(null);
  const [paging, setPaging] = useState("");
  const [pageError, setPageError] = useState("");
  const [pageRetry, setPageRetry] = useState<null | (() => Promise<void>)>(null);
  const pageRequest = useRef(0);
  const operation = useRef<symbol | null>(null);
  const [retry, setRetry] = useState<null | (() => Promise<void>)>(null);
  const epoch = useRef(0);
  const dirtyRef = useRef(false);
  const editorDirty = useRef(false);
  const feedbackDirty = useRef(new Set<string>());
  const busyRef = useRef(false);
  const requests = useRef(new Map<string, string>());
  const queryRef = useRef("");
  const scrollToLatest = useRef(true);
  const lastQuery = useRef("");
  const chatEnd = useRef<HTMLDivElement>(null);
  const changeDirty = useCallback((value: boolean) => { editorDirty.current = value; dirtyRef.current = value || feedbackDirty.current.size > 0; setDirty(dirtyRef.current); }, []);
  const changeFeedbackDirty = useCallback((key: string, value: boolean) => { if (value) feedbackDirty.current.add(key); else feedbackDirty.current.delete(key); dirtyRef.current = editorDirty.current || feedbackDirty.current.size > 0; setDirty(dirtyRef.current); }, []);

  const clearPrivate = useCallback((clearSession: boolean) => {
    ++epoch.current; operation.current = null; busyRef.current = false; setBusy(""); setLoading(false);
    setDetail(null); setItems([]); setListCursor(null); ++pageRequest.current; setPaging(""); setPageRetry(null); setQuestion(""); setNewDossier(false); setDocumentImport(null); setUploadingDocument(false); changeDirty(false);
    ++citationRequest.current; setSourcePreview(null); setSourceError(""); setLocating(null);
    if (clearSession) { setSession(null); requests.current.clear(); setRetry(null); }
  }, [changeDirty]);
  const load = useCallback(async () => {
    const current = ++epoch.current; requests.current.clear();
    if (revisionCheckId && !revisionPanel) { clearPrivate(false); setError("修回核对链接缺少正确视图，请从资料重新打开。"); return; }
    ++citationRequest.current; setSourcePreview(null); setSourceError(""); setLocating(null);
    operation.current = null; busyRef.current = false; setBusy(""); ++pageRequest.current; setPaging(""); setPageError(""); setPageRetry(null); setListCursor(null);
    setLoading(true); setNewDossier(false); setError(""); setItems([]); setDetail(null); setDocumentImport(null); setUploadingDocument(false); setQuestion(""); setNotice(""); setRetry(null); changeDirty(false);
    try {
      const nextSession = await readJSON<Session>("/api/publishing/session");
      if (current !== epoch.current) return;
      if (!["editor", "chief_editor"].includes(nextSession.user.role)) throw new LibraryError(403, "内部资料仅向编辑和主编开放。请返回登录页切换身份。");
      setSession(nextSession);
      const initialListRequest = pageRequest.current;
      const [list, dossier, imported] = await Promise.all([
        readJSON<Page<DossierItem>>(dossierListURL(queryRef.current)),
        selectedId ? readJSON<Dossier>(`/api/dossiers/${encodeURIComponent(selectedId)}${reviewVersionId ? `/versions/${encodeURIComponent(reviewVersionId)}` : ""}`) : Promise.resolve(null),
        importId && selectedId ? readJSON<DocumentImport>(`/api/dossiers/${encodeURIComponent(selectedId)}/imports/${encodeURIComponent(importId)}`) : Promise.resolve(null),
      ]);
      if (current !== epoch.current) return;
      if ((reviewVersionId || importId || evaluationId) && !selectedId) throw new LibraryError(404, "核对链接缺少资料标识，请从我的资料重新打开。");
      if (imported && imported.dossier_id !== selectedId) throw new LibraryError(404, "导入记录不属于当前资料。");
      if (initialListRequest === pageRequest.current) { setItems(list.items); setListCursor(list.next_cursor ?? null); }
      setDetail(dossier); setDocumentImport(imported);
    } catch (failure) {
      if (current !== epoch.current) return;
      clearPrivate(failure instanceof LibraryError && [401, 403].includes(failure.status));
      setError((failure as Error).message);
    } finally { if (current === epoch.current) setLoading(false); }
  }, [selectedId, reviewVersionId, importId, evaluationId, revisionPanel, revisionCheckId, clearPrivate, changeDirty]);
  const invalidate = useCallback(() => { ++epoch.current; requests.current.clear(); operation.current = null; busyRef.current = false; }, []);
  // The route identifies the external snapshot; each load clears the previous object's private data.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); return invalidate; }, [load, invalidate]);
  useEffect(() => {
    const route = window.location.pathname + window.location.search;
    const moved = () => { if (window.location.pathname + window.location.search !== route) invalidate(); };
    window.addEventListener("popstate", moved);
    return () => window.removeEventListener("popstate", moved);
  }, [invalidate, selectedId, reviewVersionId, importId, evaluationId]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirtyRef.current || busyRef.current) warnBeforeUnload(event); };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  useEffect(() => { if (scrollToLatest.current) chatEnd.current?.scrollIntoView({ block: "nearest" }); scrollToLatest.current = true; }, [detail?.messages.length]);
  useEffect(() => {
    if (lastQuery.current === query) return;
    lastQuery.current = query;
    const timer = setTimeout(() => { void pageList(true); }, 300);
    return () => clearTimeout(timer);
    // Only search text schedules this read; manuscript/form state stays intact.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  function leaveAllowed() { return (!busyRef.current || busy === "assist") && (!dirtyRef.current || window.confirm("当前资料尚未保存。离开并放弃这些修改？")); }
  function guardLinks(event: MouseEvent<HTMLDivElement>) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    if (!link || link.hasAttribute("download") || link.target === "_blank" || link.hash === "#library-main") return;
    const target = new URL(link.href, window.location.href);
    const sameRoute = target.pathname === window.location.pathname && target.search === window.location.search;
    if (sameRoute && !newDossier) return;
    if (!leaveAllowed()) { event.preventDefault(); return; }
    if (sameRoute) { event.preventDefault(); setNewDossier(false); setDrawer(false); void load(); return; }
    invalidate(); setBusy(""); ++pageRequest.current; setPaging(""); setPageError(""); ++citationRequest.current; setSourcePreview(null); setSourceError(""); setLocating(null); setDetail(null); setQuestion(""); setDrawer(false); setNewDossier(false); setUploadingDocument(false); setDocumentImport(null); setRetry(null); changeDirty(false);
  }
  function startNew() {
    if (!leaveAllowed()) return;
    invalidate(); setBusy(""); ++pageRequest.current; setPaging(""); setPageError(""); ++citationRequest.current; setSourcePreview(null); setSourceError(""); setLocating(null); setNewDossier(true); setDocumentImport(null); setUploadingDocument(false); setDrawer(false); setError(""); setNotice(""); setRetry(null); changeDirty(false);
  }
  function startDocumentUpload() {
    if (!detail?.is_current || !leaveAllowed()) return;
    invalidate(); setBusy(""); ++pageRequest.current; setPaging(""); setPageError(""); ++citationRequest.current; setSourcePreview(null); setSourceError(""); setLocating(null); setUploadingDocument(true); setError(""); setRetry(null); changeDirty(false);
  }
  async function uploadDocument(file: Upload) {
    if (!detail) return;
    const snapshot = detail; const current = epoch.current;
    await run("import", async () => {
      const result = await post<{ import_id: string; dossier_id: string }>(`/api/dossiers/${snapshot.id}/imports`, { expected_revision: snapshot.revision, version_id: snapshot.version_id, file, authorized_material: true });
      if (current !== epoch.current) return;
      changeDirty(false); setUploadingDocument(false); router.push(`/library/imports/${result.import_id}?dossier=${result.dossier_id}`);
    });
  }
  async function confirmImport(data: DossierData, materialOnly: boolean) {
    if (!documentImport || !detail) return;
    const snapshot = documentImport; const current = epoch.current;
    await run("confirm-import", async () => {
      const result = await post<{ dossier_id: string; version_id: string }>(`/api/dossiers/${snapshot.dossier_id}/imports/${snapshot.id}/${materialOnly ? "save-material" : "confirm"}`, { expected_revision: snapshot.base_revision, digest: snapshot.digest, data, acknowledged: true });
      if (current !== epoch.current) return;
      setDocumentImport(previous => previous && previous.id === snapshot.id ? { ...previous, confirmed_version_id: result.version_id, editable: false } : previous);
      changeDirty(false); router.push(`/library?dossier=${result.dossier_id}`);
    });
  }
  async function post<T>(path: string, data: object): Promise<T> {
    if (!session) throw new LibraryError(401, "请先登录。");
    const key = `${epoch.current}:${session.user.id}:${session.journal.id}:${path}:${JSON.stringify(data)}`;
    let requestId = requests.current.get(key);
    if (!requestId) { requestId = newRequestId(); requests.current.set(key, requestId); }
    const result = await readJSON<T>(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ request_id: requestId, ...data }) });
    requests.current.delete(key);
    return result;
  }
  async function run(label: string, action: () => Promise<void>, readOnly: () => boolean = () => false, reauthorize = false) {
    if (busyRef.current) return;
    const current = epoch.current;
    const token = Symbol(label); operation.current = token;
    busyRef.current = true; setBusy(label); setError(""); setNotice(""); setRetry(null);
    try {
      if (reauthorize) {
        const authorized = await readJSON<Session>("/api/publishing/session");
        if (!session || authorized.user.id !== session.user.id || authorized.journal.id !== session.journal.id || authorized.user.role !== session.user.role || authorized.csrf_token !== session.csrf_token) throw new LibraryError(401, "登录身份已变化，请重新载入；未重试旧请求。");
      }
      if (current === epoch.current) await action();
    }
    catch (failure) {
      if (current !== epoch.current) return;
      const status = failure instanceof LibraryError ? failure.status : -1;
      if ([401, 403, 404].includes(status)) clearPrivate(status !== 404);
      if (status === 0 || readOnly()) {
        // Hide stale private documents and transcript until authorization can be checked again.
        setDetail(null); setDocumentImport(null); setQuestion(""); setSourcePreview(null); setSourceError(""); ++citationRequest.current; setLocating(null);
      }
      setError(`${readOnly() ? "操作已保存。" : ""}${(failure as Error).message}`);
      if (status === 0 || status === 429 || status >= 500) {
        setRetryLabel(readOnly() ? "重试读取" : "重试原请求");
        setRetry(() => () => run(label, action, readOnly, true));
      }
    } finally { if (operation.current === token) { operation.current = null; busyRef.current = false; setBusy(""); } }
  }
  async function refreshAfter(id: string, current: number, versionId?: string) {
    const filter = queryRef.current; const listRequest = pageRequest.current;
    const [next, list] = await Promise.all([
      readJSON<Dossier>(`/api/dossiers/${encodeURIComponent(id)}${versionId ? `/versions/${encodeURIComponent(versionId)}` : ""}`),
      readJSON<Page<DossierItem>>(dossierListURL(queryRef.current)),
    ]);
    if (current !== epoch.current) return;
    setDetail(next);
    if (queryRef.current === filter && listRequest === pageRequest.current) { setItems(list.items); setListCursor(list.next_cursor ?? null); }
    setSourcePreview(null); setSourceError(""); changeDirty(false);
  }
  async function save(data: DossierData, file: Upload | null) {
    if (!detail) return;
    const snapshot = detail; const current = epoch.current;
    let committed = false;
    await run("save", async () => {
      if (!committed) { await post(`/api/dossiers/${snapshot.id}/versions`, { expected_revision: snapshot.revision, data, file }); committed = true; if (current === epoch.current) changeDirty(false); }
      await refreshAfter(snapshot.id, current);
      if (current === epoch.current) setNotice("新版本已保存，请重新核对。");
    }, () => committed);
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = { title: String(data.get("title") || ""), source_kind: String(data.get("source_kind")), source_note: String(data.get("source_note") || ""), authorized_material: data.get("authorized_material") === "on" };
    const current = epoch.current;
    await run("create", async () => {
      const result = await post<{ dossier_id: string }>("/api/dossiers", payload);
      if (current !== epoch.current) return;
      changeDirty(false); setNewDossier(false); router.push(`/library?dossier=${result.dossier_id}`);
    });
  }
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail || !question.trim()) return;
    const snapshot = detail; const message = question.trim(); const current = epoch.current;
    await run("assist", async () => {
      const reply = await post<Message>(`/api/dossiers/${snapshot.id}/chat`, { expected_revision: snapshot.revision, version_id: snapshot.version_id, message });
      if (current !== epoch.current) return;
      setDetail(previous => {
        const base = previous ?? snapshot;
        return base.id === snapshot.id && base.version_id === snapshot.version_id ? { ...base, messages: base.messages.some(item => item.id === reply.id) ? base.messages : [...base.messages, reply] } : previous;
      });
      setQuestion("");
    });
  }
  async function locateCitation(citation: Citation, trigger: HTMLButtonElement) {
    if (!detail) return;
    const dossierId = detail.id; const current = epoch.current; const request = ++citationRequest.current;
    citationTrigger.current = trigger;
    setLocating(`${citation.version_id}:${citation.source_id}`); setSourcePreview(null); setSourceError("");
    try {
      const snapshot = await readJSON<Dossier>(`/api/dossiers/${encodeURIComponent(dossierId)}/versions/${encodeURIComponent(citation.version_id)}`);
      if (current !== epoch.current || request !== citationRequest.current) return;
      if (snapshot.id !== dossierId || citationText(snapshot, citation) === null) throw new LibraryError(409, "引用与原版内容不匹配，请重新载入资料后再定位。");
      setSourcePreview({ snapshot, citation });
    } catch (failure) {
      if (current !== epoch.current || request !== citationRequest.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { clearPrivate(failure.status !== 404); setError(failure.message); return; }
      setSourceError((failure as Error).message);
    } finally { if (current === epoch.current && request === citationRequest.current) setLocating(null); }
  }
  async function pageList(reset: boolean) {
    const current = epoch.current; const request = ++pageRequest.current;
    const cursor = reset ? null : listCursor;
    setPaging("list"); setPageError(""); setPageRetry(null); if (reset) { setItems([]); setListCursor(null); }
    try {
      const page = await readJSON<Page<DossierItem>>(dossierListURL(queryRef.current, cursor));
      if (current !== epoch.current || request !== pageRequest.current) return;
      setItems(previous => reset ? page.items : [...previous, ...page.items.filter(item => !previous.some(old => old.id === item.id))]);
      setListCursor(page.next_cursor ?? null);
    } catch (failure) {
      if (current !== epoch.current || request !== pageRequest.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { clearPrivate(failure.status !== 404); setError(failure.message); return; }
      setPageError((failure as Error).message); setPageRetry(() => () => pageList(reset));
    } finally { if (current === epoch.current && request === pageRequest.current) setPaging(""); }
  }
  async function pageMessages() {
    if (!detail?.messages_next_cursor || paging) return;
    const snapshot = detail; const current = epoch.current;
    const request = ++pageRequest.current;
    setPaging("messages"); setPageError(""); setPageRetry(null);
    try {
      const page = await readJSON<Page<Message>>(`/api/dossiers/${snapshot.id}/messages?cursor=${encodeURIComponent(snapshot.messages_next_cursor!)}`);
      if (current !== epoch.current || request !== pageRequest.current) return;
      scrollToLatest.current = false;
      setDetail(previous => previous?.id === snapshot.id ? { ...previous, messages: [...page.items.filter(item => !previous.messages.some(old => old.id === item.id)), ...previous.messages], messages_next_cursor: page.next_cursor } : previous);
    } catch (failure) {
      if (current !== epoch.current || request !== pageRequest.current) return;
      if (failure instanceof LibraryError && [401, 403, 404].includes(failure.status)) { clearPrivate(failure.status !== 404); setError(failure.message); return; }
      setPageError((failure as Error).message); setPageRetry(() => pageMessages);
    } finally { if (current === epoch.current && request === pageRequest.current) setPaging(""); }
  }

  async function confirm() {
    if (!detail) return;
    const snapshot = detail; const current = epoch.current;
    let committed = false;
    await run("confirm", async () => {
      if (!committed) { await post(`/api/dossiers/${snapshot.id}/confirm`, { expected_revision: snapshot.revision, version_id: snapshot.version_id, digest: snapshot.content_digest, acknowledged: true }); committed = true; }
      await refreshAfter(snapshot.id, current, snapshot.version_id);
      if (current === epoch.current) setNotice("当前版本已由本人核对。");
    }, () => committed);
  }

  if (loading && !session) return <main className={styles.gate}><p role="status">正在恢复登录…</p></main>;
  if (!session) return <main className={styles.gate}><h1>内部资料</h1><p role="alert">{error || "请先登录后打开内部资料。"}</p><Link href="/">返回登录</Link><button type="button" onClick={() => void load()}>重试连接</button></main>;

  const configuredModel = detail?.model;
  const modelLabel = configuredModel?.provider === "deepseek" ? "DeepSeek · 只读审阅" : configuredModel?.provider === "mock" ? "Mock · 模拟审阅" : "模型状态待确认";
  const modelBlocked = configuredModel?.ready === false;
  const historicalVersion = detail !== null && !detail.is_current;
  return <div className={styles.workspace} onClickCapture={guardLinks}>
    <a href="#library-main" className={styles.skip}>跳到对话</a>
    <aside className={`${styles.sidebar} ${drawer ? styles.drawerOpen : ""}`} aria-label="我的资料">
      <div className={styles.brand}><Link href="/">Pivot</Link><button className={styles.mobileOnly} aria-label="关闭资料列表" onClick={() => setDrawer(false)}><Glyph name="close" /></button></div>
      <GlobalSearch scope={`${session.journal.id}:${session.user.id}:${session.user.role}:${session.csrf_token}`} onQueryChange={value => { setQuery(value); queryRef.current = value; ++pageRequest.current; setItems([]); setListCursor(null); setPaging("list"); setPageError(""); setPageRetry(null); }} />
      <div className={styles.sideHeading}><h2>我的资料</h2><button type="button" onClick={startNew}>新建资料</button></div>
      <nav className={styles.list} aria-busy={paging === "list"}>
        {paging === "list" && !items.length && <p role="status">正在查找资料…</p>}
        {items.map(item => <Link key={item.id} href={`/library?dossier=${item.id}`} aria-current={selectedId === item.id && !newDossier ? "page" : undefined} className={styles.listItem}><Glyph name="file" /><span>{item.title || "未命名资料"}<small>v{item.version_no} · {item.verified ? "已核对" : "待核对"}</small></span></Link>)}
        {!items.length && !loading && !paging && <p className={styles.hint}>{query ? "没有匹配的资料。" : "尚无资料，先新建一份。"}</p>}
        {listCursor && <button type="button" disabled={!!paging} onClick={() => void pageList(false)}>{paging === "list" ? "正在加载…" : "加载更多资料"}</button>}

      </nav>
      <PersonalCalendar scope={`${session.journal.id}:${session.user.id}:${session.user.role}:${session.csrf_token}`} /><div className={styles.identity}><IdentityControl user={session.user} /><SettingsButton onOpen={() => setDrawer(false)} /><Link href="/">返回主工作台</Link></div>
    </aside>
    <div className={styles.main}>
      <header className={styles.toolbar}><button className={styles.mobileOnly} aria-label="打开资料列表" onClick={() => setDrawer(true)}><Glyph name="inbox" /></button><h1>内部资料</h1><span>不构成正式投稿</span><Link href="/publishing">出版工作区</Link></header>
      {error && <div className={styles.alert} role="alert">{error} {retry ? <button disabled={!!busy} onClick={() => void retry()}>{retryLabel}</button> : <button disabled={!!busy} onClick={() => { if (leaveAllowed()) void load(); }}>重新载入</button>}</div>}
      {pageError && <div className={styles.alert} role="alert">{pageError} {pageRetry && <button disabled={!!paging} onClick={() => void pageRetry()}>重试加载</button>}</div>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}
      <div className={styles.columns}>
        <main className={styles.chat} id="library-main" tabIndex={-1}>
          <div className={styles.chatHeader}><h2>{detail?.data.title || "资料对话"}</h2><p>{modelBlocked ? "模型未就绪，请检查服务配置后重新载入。" : `${modelLabel} · 结论待人工复核`}</p></div>
          <div className={styles.transcript} aria-label="资料对话历史" aria-busy={busy === "assist"}>
            {detail?.messages_next_cursor && <button type="button" disabled={!!paging} onClick={() => void pageMessages()}>{paging === "messages" ? "正在加载…" : "加载较早对话"}</button>}
            {loading ? <p role="status">正在载入资料…</p> : !detail ? <div className={styles.empty}><Glyph name="file" size={28} /><h2>从资料开始</h2><p>选择或新建资料，围绕已保存的全文与作者信息提问。</p></div> : !detail.messages.length ? <div className={styles.empty}><h2>从哪一处开始审阅？</h2><p>回答依据当前已保存资料。点击结论后的引用，可核对原版全文或作者字段；资料不足时不会补造结论。</p><button onClick={() => { setRetry(null); setQuestion("请概括这份全文的研究方法，并引用原文。"); }}>审阅研究方法</button></div> : detail.messages.map(message => <MessageTurn key={message.id} message={message} feedback={{ dossierId: detail.id, session, onDirty: changeFeedbackDirty, onDenied: () => { clearPrivate(true); setError("访问权限或身份已变化，请重新登录。"); } }} currentVersionId={detail.version_id} locating={locating} onCitation={(citation, trigger) => void locateCitation(citation, trigger)} />)}
            <div ref={chatEnd} />
          </div>
          {detail && !newDossier && !loading && !historicalVersion && <NextSteps key={`${detail.id}:${detail.version_id}:${detail.revision}:${session.user.role}:${detail.messages.at(-1)?.id}`} url={`/api/dossiers/${detail.id}/guidance`} objectId={detail.id} versionId={detail.version_id} revision={detail.revision} role={session.user.role} disabled={!!busy || modelBlocked} onChoose={prompt => { const next = question.trim() ? `${question}\n\n${prompt}` : prompt; if (next.length > 2000) { setError("输入已较长，请先发送或清理当前草稿，再选择建议。"); return; } setRetry(null); setQuestion(next); document.getElementById("library-question")?.focus(); }} />}
          <form className={styles.composer} onSubmit={send}><label htmlFor="library-question" className={styles.srOnly}>询问当前资料</label><textarea id="library-question" name="question" value={question} maxLength={2000} onChange={event => { setRetry(null); setQuestion(event.target.value); }} disabled={!detail || newDossier || !!busy || loading || modelBlocked || historicalVersion} rows={3} placeholder={historicalVersion ? "历史版本只读，请返回当前资料提问" : "询问当前全文、作者或文献来源…"} /><div><span>{detail ? `${detail.is_current ? "当前" : "历史"} v${detail.version_no}${documentImport && !documentImport.confirmed_version_id ? " · 导入候选核对保存后参与问答" : dirty ? " · 有未保存修改，回答依据已保存版本" : ""}` : "先选择资料"}</span><button type="submit" className={styles.primary} disabled={!detail || newDossier || !question.trim() || !!busy || loading || modelBlocked || historicalVersion}>{busy === "assist" ? "回复中…" : "发送"}<Glyph name="arrow" size={16} /></button></div><p className={styles.boundary}>邮件与关键决定须负责人确认。</p></form>
        </main>
        <section className={styles.material} aria-label={importId ? "独立导入核对" : reviewVersionId ? "独立版本核对" : "资料内容"}>
          {sourceError && <p className={styles.sourceError} role="alert">{sourceError}</p>}
          <div className={styles.materialView} hidden={sourcePreview !== null}>
          {uploadingDocument ? <DocumentUpload busy={!!busy} onUpload={uploadDocument} onCancel={() => { if (leaveAllowed()) { setUploadingDocument(false); changeDirty(false); } }} onDirty={value => { setRetry(null); changeDirty(value); }} /> : documentImport && detail ? <ImportReview key={`${documentImport.id}:${documentImport.digest}`} imported={documentImport} detail={detail} busy={!!busy} onDirty={value => { setRetry(null); changeDirty(value); }} onConfirm={confirmImport} /> : newDossier ? <><div className={styles.materialHeader}><h2>新建资料</h2><button disabled={!!busy} onClick={() => { if (leaveAllowed()) { setNewDossier(false); changeDirty(false); } }}>取消</button></div><form className={styles.form} onSubmit={create} onChange={() => { setRetry(null); changeDirty(true); }}><label>题名<input name="title" required maxLength={500} autoComplete="off" /></label><label>资料类型<select name="source_kind" defaultValue="synthetic"><option value="synthetic">合成资料</option><option value="public_authorized">公开 / 已获授权资料</option></select></label><label>来源与授权说明<textarea name="source_note" required minLength={5} maxLength={2000} rows={4} /></label><label className={styles.checkbox}><input type="checkbox" name="authorized_material" required /><span>我确认仅录入合成或公开已获授权资料，不包含保密稿件。</span></label><button className={styles.primary} disabled={!!busy}>{busy === "create" ? "创建中…" : "创建资料"}</button></form></> : detail ? evaluationId ? <EvaluationReview key={`${detail.id}:${evaluationId}:${session.csrf_token}`} packageId={evaluationId} context={{ dossierId: detail.id, session, onDirty: changeFeedbackDirty, onDenied: () => { clearPrivate(true); setError("访问权限或身份已变化，请重新登录。"); } }} /> : revisionPanel ? <RevisionCheck key={`${detail.id}:${detail.version_id}:${session.csrf_token}:${revisionCheckId ?? "new"}`} detail={detail} session={session} checkId={revisionCheckId} onDirty={value => changeFeedbackDirty(`revision:${detail.id}:${detail.version_id}:${detail.revision}:${session.csrf_token}:${revisionCheckId ?? "new"}`, value)} onDenied={() => { clearPrivate(true); setError("访问权限或身份已变化，请重新登录。"); }} /> : reviewVersionId ? <DossierReview key={detail.version_id} detail={detail} busy={!!busy} confirming={busy === "confirm"} onConfirm={confirm} onUnavailable={failure => { clearPrivate(failure.status !== 404); setError(failure.message); }} /> : <><div className={styles.materialHeader}><div role="tablist" aria-label="资料视图">{([['metadata', '资料'], ['text', '原文'], ['versions', '版本']] as const).map(([id, label]) => <button key={id} id={`library-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`library-panel-${id}`} tabIndex={tab === id ? 0 : -1} onKeyDown={event => { const all = ["metadata", "text", "versions"] as const; const index = all.indexOf(tab); if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = all[(index + (event.key === "ArrowRight" ? 1 : 2)) % 3]; setTab(next); document.getElementById(`library-tab-${next}`)?.focus(); } }} onClick={() => setTab(id)}>{label}</button>)}</div><span>v{detail.version_no} · {detail.verified ? "已核对" : "待核对"}</span>{detail.is_current && <button type="button" className={styles.documentImportButton} disabled={!!busy} onClick={startDocumentUpload}>导入 PDF / Word</button>}</div><div role="tabpanel" id={`library-panel-${tab}`} aria-labelledby={`library-tab-${tab}`} className={styles.materialBody}>
            {tab === "metadata" && <div className={styles.materialActions}><Link href={`/library?dossier=${detail.id}&panel=revisions`}>修回核对</Link><MetadataExport key={`${detail.id}:${detail.version_id}:${session.csrf_token}`} detail={detail} session={session} onDenied={() => { clearPrivate(true); setError("访问权限或身份已变化，请重新登录。"); }} /></div>}
            <DossierEditor key={`${detail.id}:${detail.version_id}`} detail={detail} hidden={tab !== "metadata"} busy={!!busy} saving={busy === "save"} onDirty={value => { setRetry(null); changeDirty(value); }} onSave={save} />
            {tab === "text" && <OriginalText detail={detail} />}
            {tab === "versions" && <><VersionList key={`${detail.id}:${detail.revision}:${detail.verification?.id ?? ""}`} detail={detail} onUnavailable={failure => { clearPrivate(failure.status !== 404); setError(failure.message); }} /><ImportHistory key={`${detail.id}:${detail.revision}`} dossierId={detail.id} revision={detail.revision} onUnavailable={failure => { clearPrivate(failure.status !== 404); setError(failure.message); }} /></>}
          </div><footer className={styles.materialFooter}><span>{dirty ? "有未保存修改" : detail.missing.length ? `${detail.missing.length} 项待补充` : "资料已齐全"}</span>{dirty ? <span>保存后可核对新版本</span> : <Link href={`/library/review/${detail.version_id}?dossier=${detail.id}`}>核对本版资料<Glyph name="arrow" size={16} /></Link>}</footer></> : <div className={styles.empty}><h2>资料内容</h2><p>题名、作者和原文会显示在这里。</p>{!loading && <button onClick={startNew}>新建资料</button>}</div>}
          </div>
          {sourcePreview && detail && <EvidencePanel snapshot={sourcePreview.snapshot} citation={sourcePreview.citation} currentVersionId={detail.version_id} onClose={() => { setSourcePreview(null); const trigger = citationTrigger.current; requestAnimationFrame(() => { if (trigger?.isConnected) trigger.focus({ preventScroll: true }); }); }} />}
        </section>
      </div>
    </div>
  </div>;
}
