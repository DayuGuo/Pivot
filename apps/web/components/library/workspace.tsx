"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import Glyph from "../editorial/icons";
import { LibraryError, readJSON } from "./api";
import DossierEditor from "./editor";
import DossierReview from "./review";
import { OriginalText, VersionList } from "./viewers";
import type { Dossier, DossierData, DossierItem, Message, Session, Upload } from "./types";
import styles from "./library.module.css";

export default function LibraryWorkspace({ reviewVersionId }: { reviewVersionId?: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const selectedId = search.get("dossier");
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<DossierItem[]>([]);
  const [detail, setDetail] = useState<Dossier | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [newDossier, setNewDossier] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState<"metadata" | "text" | "versions">("metadata");
  const [question, setQuestion] = useState("");
  const [query, setQuery] = useState("");
  const [dirty, setDirty] = useState(false);
  const [retry, setRetry] = useState<null | (() => Promise<void>)>(null);
  const epoch = useRef(0);
  const dirtyRef = useRef(false);
  const busyRef = useRef(false);
  const requests = useRef(new Map<string, string>());
  const chatEnd = useRef<HTMLDivElement>(null);
  const changeDirty = useCallback((value: boolean) => { dirtyRef.current = value; setDirty(value); }, []);

  const clearPrivate = useCallback((clearSession: boolean) => {
    setDetail(null); setItems([]); setQuestion(""); setNewDossier(false); changeDirty(false);
    if (clearSession) { setSession(null); requests.current.clear(); setRetry(null); }
  }, [changeDirty]);
  const load = useCallback(async () => {
    const current = ++epoch.current;
    setLoading(true); setError(""); setItems([]); setDetail(null); setQuestion(""); setNotice(""); setRetry(null); changeDirty(false);
    try {
      const nextSession = await readJSON<Session>("/api/publishing/session");
      if (current !== epoch.current) return;
      if (!["editor", "chief_editor"].includes(nextSession.user.role)) throw new LibraryError(403, "内部资料仅向编辑和主编开放。请返回登录页切换身份。");
      setSession(nextSession);
      const [list, dossier] = await Promise.all([
        readJSON<{ items: DossierItem[] }>("/api/dossiers"),
        selectedId ? readJSON<Dossier>(`/api/dossiers/${encodeURIComponent(selectedId)}${reviewVersionId ? `/versions/${encodeURIComponent(reviewVersionId)}` : ""}`) : Promise.resolve(null),
      ]);
      if (current !== epoch.current) return;
      if (reviewVersionId && !selectedId) throw new LibraryError(404, "核对链接缺少资料标识，请从我的资料重新打开。");
      setItems(list.items); setDetail(dossier);
    } catch (failure) {
      if (current !== epoch.current) return;
      clearPrivate(failure instanceof LibraryError && [401, 403].includes(failure.status));
      setError((failure as Error).message);
    } finally { if (current === epoch.current) setLoading(false); }
  }, [selectedId, reviewVersionId, clearPrivate, changeDirty]);
  const invalidate = useCallback(() => { ++epoch.current; }, []);
  // The route identifies the external snapshot; each load clears the previous object's private data.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); return invalidate; }, [load, invalidate]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirtyRef.current || busyRef.current) event.preventDefault(); };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  useEffect(() => { chatEnd.current?.scrollIntoView({ block: "nearest" }); }, [detail?.messages.length]);

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
    ++epoch.current; setDetail(null); setQuestion(""); setDrawer(false); setNewDossier(false); setRetry(null); changeDirty(false);
  }
  function startNew() {
    if (!leaveAllowed()) return;
    ++epoch.current; setNewDossier(true); setDrawer(false); setError(""); setNotice(""); setRetry(null); changeDirty(false);
  }
  async function post<T>(path: string, data: object): Promise<T> {
    if (!session) throw new LibraryError(401, "请先登录。");
    const key = `${path}:${JSON.stringify(data)}`;
    let requestId = requests.current.get(key);
    if (!requestId) { requestId = crypto.randomUUID(); requests.current.set(key, requestId); }
    const result = await readJSON<T>(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ request_id: requestId, ...data }) });
    return result;
  }
  async function run(label: string, action: () => Promise<void>) {
    if (busyRef.current) return;
    const current = epoch.current;
    busyRef.current = true; setBusy(label); setError(""); setNotice(""); setRetry(null);
    try { await action(); requests.current.clear(); }
    catch (failure) {
      if (current !== epoch.current) return;
      const status = failure instanceof LibraryError ? failure.status : -1;
      if ([401, 403, 404].includes(status)) clearPrivate(status !== 404);
      if (status === 0) {
        // Hide stale private documents and transcript until authorization can be checked again.
        setDetail(null); setQuestion("");
      }
      setError((failure as Error).message);
      if (status === 0 || status >= 500) setRetry(() => () => run(label, action));
    } finally { busyRef.current = false; setBusy(""); }
  }
  async function refreshAfter(id: string, current: number, versionId?: string) {
    const [next, list] = await Promise.all([
      readJSON<Dossier>(`/api/dossiers/${encodeURIComponent(id)}${versionId ? `/versions/${encodeURIComponent(versionId)}` : ""}`),
      readJSON<{ items: DossierItem[] }>("/api/dossiers"),
    ]);
    if (current !== epoch.current) return;
    setDetail(next); setItems(list.items); changeDirty(false);
  }
  async function save(data: DossierData, file: Upload | null) {
    if (!detail) return;
    const snapshot = detail; const current = epoch.current;
    await run("save", async () => {
      await post(`/api/dossiers/${snapshot.id}/versions`, { expected_revision: snapshot.revision, data, file });
      await refreshAfter(snapshot.id, current);
      if (current === epoch.current) setNotice("新版本已保存，请重新核对。");
    });
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = { title: String(data.get("title") || ""), source_kind: String(data.get("source_kind")), source_note: String(data.get("source_note") || ""), authorized_material: data.get("authorized_material") === "on" };
    await run("create", async () => {
      const result = await post<{ dossier_id: string }>("/api/dossiers", payload);
      changeDirty(false); setNewDossier(false); router.push(`/library?dossier=${result.dossier_id}`);
    });
  }
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail || !question.trim()) return;
    const snapshot = detail; const message = question.trim(); const current = epoch.current;
    await run("assist", async () => {
      const reply = await post<Message>(`/api/dossiers/${snapshot.id}/assist`, { expected_revision: snapshot.revision, version_id: snapshot.version_id, message });
      if (current !== epoch.current) return;
      setDetail(previous => {
        const base = previous ?? snapshot;
        return base.id === snapshot.id && base.version_id === snapshot.version_id ? { ...base, messages: base.messages.some(item => item.id === reply.id) ? base.messages : [...base.messages, reply] } : previous;
      });
      setQuestion("");
    });
  }
  async function confirm() {
    if (!detail) return;
    const snapshot = detail; const current = epoch.current;
    await run("confirm", async () => {
      await post(`/api/dossiers/${snapshot.id}/confirm`, { expected_revision: snapshot.revision, version_id: snapshot.version_id, digest: snapshot.content_digest, acknowledged: true });
      await refreshAfter(snapshot.id, current, snapshot.version_id);
      if (current === epoch.current) setNotice("当前版本已由本人核对。");
    });
  }

  if (loading && !session) return <main className={styles.gate}><p role="status">正在恢复登录…</p></main>;
  if (!session) return <main className={styles.gate}><h1>内部资料</h1><p role="alert">{error || "请先登录后打开内部资料。"}</p><Link href="/">返回登录</Link><button type="button" onClick={() => void load()}>重试连接</button></main>;

  return <div className={styles.workspace} onClickCapture={guardLinks}>
    <a href="#library-main" className={styles.skip}>跳到对话</a>
    <aside className={`${styles.sidebar} ${drawer ? styles.drawerOpen : ""}`} aria-label="我的资料">
      <div className={styles.brand}><Link href="/">Pivot</Link><button className={styles.mobileOnly} aria-label="关闭资料列表" onClick={() => setDrawer(false)}><Glyph name="close" /></button></div>
      <div className={styles.sideHeading}><h2>我的资料</h2><button type="button" onClick={startNew}>新建资料</button></div>
      <label className={styles.search}><Glyph name="search" /><input aria-label="搜索我的资料" name="search" autoComplete="off" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索题名…" /></label>
      <nav className={styles.list}>
        {items.filter(item => item.title.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(item => <Link key={item.id} href={`/library?dossier=${item.id}`} aria-current={selectedId === item.id && !newDossier ? "page" : undefined} className={styles.listItem}><Glyph name="file" /><span>{item.title || "未命名资料"}<small>v{item.version_no} · {item.verified ? "已核对" : "待核对"}</small></span></Link>)}
        {!items.length && !loading && <p className={styles.hint}>尚无资料，先新建一份。</p>}
      </nav>
      <div className={styles.identity}><span>{session.user.name}</span><small>{session.journal.name}</small><Link href="/">返回登录 / 切换身份</Link></div>
    </aside>
    <div className={styles.main}>
      <header className={styles.toolbar}><button className={styles.mobileOnly} aria-label="打开资料列表" onClick={() => setDrawer(true)}><Glyph name="inbox" /></button><h1>内部资料</h1><span>不构成正式投稿</span><Link href="/publishing">出版工作区</Link></header>
      {error && <div className={styles.alert} role="alert">{error} {retry ? <button disabled={!!busy} onClick={() => void retry()}>重试原请求</button> : <button disabled={!!busy} onClick={() => { if (leaveAllowed()) void load(); }}>重新载入</button>}</div>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}
      <div className={styles.columns}>
        <main className={styles.chat} id="library-main" tabIndex={-1}>
          <div className={styles.chatHeader}><h2>{detail?.data.title || "资料对话"}</h2><p>规则引导 · 未调用模型</p></div>
          <div className={styles.transcript} aria-label="资料对话历史" aria-busy={busy === "assist"}>
            {loading ? <p role="status">正在载入资料…</p> : !detail ? <div className={styles.empty}><Glyph name="file" size={28} /><h2>从资料开始</h2><p>选择或新建资料，再查看缺项与下一步。</p></div> : !detail.messages.length ? <div className={styles.empty}><h2>还需要补充什么？</h2><p>可询问缺项、资料状态、版本和下一步。规则引导不进行全文科学审阅。</p><button onClick={() => setQuestion("这份资料还缺少什么？")}>查看当前缺项</button></div> : detail.messages.map(message => <article className={styles.turn} key={message.id}><p className={styles.userQuestion}>{message.question}</p><small>v{message.version_no} · 规则引导 · 未调用模型</small><div className={styles.answer}>{message.answer}</div></article>)}
            <div ref={chatEnd} />
          </div>
          <form className={styles.composer} onSubmit={send}><label htmlFor="library-question" className={styles.srOnly}>询问当前资料</label><textarea id="library-question" name="question" value={question} maxLength={2000} onChange={event => setQuestion(event.target.value)} disabled={!detail || newDossier || !!busy || loading} rows={3} placeholder="询问缺项、资料状态、版本或下一步…" /><div><span>{detail ? `当前 v${detail.version_no}${dirty ? " · 有未保存修改，回答依据已保存版本" : ""}` : "先选择资料"}</span><button type="submit" className={styles.primary} disabled={!detail || newDossier || !question.trim() || !!busy || loading}>{busy === "assist" ? "回复中…" : "发送"}<Glyph name="arrow" size={16} /></button></div></form>
        </main>
        <section className={styles.material} aria-label={reviewVersionId ? "独立版本核对" : "资料内容"}>
          {newDossier ? <><div className={styles.materialHeader}><h2>新建资料</h2><button disabled={!!busy} onClick={() => { if (leaveAllowed()) { setNewDossier(false); changeDirty(false); } }}>取消</button></div><form className={styles.form} onSubmit={create} onChange={() => changeDirty(true)}><label>题名<input name="title" required maxLength={500} autoComplete="off" /></label><label>资料类型<select name="source_kind" defaultValue="synthetic"><option value="synthetic">合成资料</option><option value="public_authorized">公开 / 已获授权资料</option></select></label><label>来源与授权说明<textarea name="source_note" required minLength={5} maxLength={2000} rows={4} /></label><label className={styles.checkbox}><input type="checkbox" name="authorized_material" required /><span>我确认仅录入合成或公开已获授权资料，不包含保密稿件。</span></label><button className={styles.primary} disabled={!!busy}>{busy === "create" ? "创建中…" : "创建资料"}</button></form></> : detail ? reviewVersionId ? <DossierReview key={detail.version_id} detail={detail} busy={!!busy} confirming={busy === "confirm"} onConfirm={confirm} /> : <><div className={styles.materialHeader}><div role="tablist" aria-label="资料视图">{([['metadata', '资料'], ['text', '原文'], ['versions', '版本']] as const).map(([id, label]) => <button key={id} id={`library-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`library-panel-${id}`} tabIndex={tab === id ? 0 : -1} onKeyDown={event => { const all = ["metadata", "text", "versions"] as const; const index = all.indexOf(tab); if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = all[(index + (event.key === "ArrowRight" ? 1 : 2)) % 3]; setTab(next); document.getElementById(`library-tab-${next}`)?.focus(); } }} onClick={() => setTab(id)}>{label}</button>)}</div><span>v{detail.version_no} · {detail.verified ? "已核对" : "待核对"}</span></div><div role="tabpanel" id={`library-panel-${tab}`} aria-labelledby={`library-tab-${tab}`} className={styles.materialBody}>
            <DossierEditor key={`${detail.id}:${detail.version_id}`} detail={detail} hidden={tab !== "metadata"} busy={!!busy} saving={busy === "save"} onDirty={changeDirty} onSave={save} />
            {tab === "text" && <OriginalText detail={detail} />}
            {tab === "versions" && <VersionList detail={detail} />}
          </div><footer className={styles.materialFooter}><span>{dirty ? "有未保存修改" : detail.missing.length ? `${detail.missing.length} 项待补充` : "资料已齐全"}</span>{dirty ? <span>保存后可核对新版本</span> : <Link href={`/library/review/${detail.version_id}?dossier=${detail.id}`}>核对本版资料<Glyph name="arrow" size={16} /></Link>}</footer></> : <div className={styles.empty}><h2>资料内容</h2><p>题名、作者和原文会显示在这里。</p>{!loading && <button onClick={startNew}>新建资料</button>}</div>}
        </section>
      </div>
    </div>
  </div>;
}
