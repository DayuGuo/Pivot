"use client";
import { requestId as newRequestId, readStorage, writeStorage, withRequestTimeout } from "../browser";

import Link from "next/link";
import NextSteps from "../assistant/next-steps";
import RevisionComparisonPanel from "../assistant/revision-comparison";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode, type MouseEvent } from "react";
import Glyph from "../editorial/icons";
import type { ChatMessage, Detail, PublishingSession, Workspace } from "./types";
import { roleLabels } from "./types";
import styles from "./publishing.module.css";

export class APIError extends Error { constructor(public status: number, message: string) { super(message); } }
type PublishingContext = {
  session: PublishingSession; workspace: Workspace | null; detail: Detail | null; selectedId: string | null;
  error: string; refreshing: boolean; refresh: () => Promise<void>; select: (id: string | null) => void;
  setReviewContext: (id: string | null) => void; setUnsaved: (dirty: boolean) => void;
  mutate: <T>(path: string, data: object, method?: "POST" | "PATCH") => Promise<T>;
};
const Context = createContext<PublishingContext | null>(null);
const EMPTY_MESSAGES: ChatMessage[] = [];
function mergeMessages(base: ChatMessage[], additional: ChatMessage[]) { const ids = new Set(base.map(message => message.id)); return [...base, ...additional.filter(message => { if (ids.has(message.id)) return false; ids.add(message.id); return true; })]; }
export function usePublishing() { const value = useContext(Context); if (!value) throw new Error("Publishing layout required"); return value; }
async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { return await withRequestTimeout(80_000, init?.signal, async signal => {
    response = await fetch(`/api/publishing${path}`, { credentials: "same-origin", cache: "no-store", ...init, signal });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      const validation = detail && typeof detail === "object" && !Array.isArray(detail) && typeof detail.message === "string" ? [detail.message, ...(Array.isArray(detail.missing) ? detail.missing.filter((item: unknown): item is { message: string } => typeof item === "object" && item !== null && "message" in item && typeof item.message === "string").map((item: { message: string }) => item.message) : [])].join("；") : null;
      throw new APIError(response.status, typeof detail === "string" ? detail : validation ?? (response.status === 422 ? "资料格式不符合要求，请检查字段长度、邮箱和文件后重试。" : "操作未完成，请重新载入后重试。"));
    }
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new APIError(502, "响应未完整收到，请重试恢复结果。");
    return body as T;
  }); } catch (failure) { if (failure instanceof APIError) throw failure; throw new APIError(0, "无法连接出版服务，请检查网络后重试；输入仍然保留。"); }
}

function subscribeTheme(listener: () => void) { window.addEventListener("publishing-theme-change", listener); window.addEventListener("storage", listener); return () => { window.removeEventListener("publishing-theme-change", listener); window.removeEventListener("storage", listener); }; }
let memoryTheme = "system";
function themeSnapshot() { const value = readStorage("localStorage", "publishing-theme") ?? memoryTheme; return value && ["light", "dark", "system"].includes(value) ? value : "system"; }

export default function PublishingWorkspace({ children }: { children: ReactNode }) {
  const router = useRouter(); const pathname = usePathname(); const search = useSearchParams();
  const [session, setSession] = useState<PublishingSession | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [reviewContext, setReviewContext] = useState<string | null>(null);
  const [error, setError] = useState(""); const [authLost, setAuthLost] = useState(false);
  const [refreshing, setRefreshing] = useState(true); const [drawer, setDrawer] = useState(false);
  const theme = useSyncExternalStore(subscribeTheme, themeSnapshot, () => "system");
  const dirty = useRef(false); const requests = useRef(new Map<string, string>()); const sequence = useRef(0);
  const previousIdentity = useRef<string | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const selectedId = (pathname.includes("/review/") || pathname.includes("/preview/") || pathname.includes("/document-imports/")) ? reviewContext : search.get("manuscript");
  const refresh = useCallback(async () => {
    refreshController.current?.abort();
    const control = new AbortController(); refreshController.current = control;
    const generation = ++sequence.current;
    let active = true;
    try {
      const nextSession = await fetchJSON<PublishingSession>("/session", { signal: control.signal });
      if (generation !== sequence.current) return;
      const identity = JSON.stringify([nextSession.journal.id, nextSession.user.id, nextSession.user.role, nextSession.csrf_token]);
      if (previousIdentity.current !== null && previousIdentity.current !== identity) {
        setWorkspace(null); setDetail(null); requests.current.clear(); dirty.current = false;
      }
      previousIdentity.current = identity;
      setSession(nextSession);
      const [nextWorkspace, nextDetail] = await Promise.all([
        fetchJSON<Workspace>("/workspace", { signal: control.signal }).then(value => { if (active && generation === sequence.current) setWorkspace(value); return value; }),
        (selectedId ? fetchJSON<Detail>(`/manuscripts/${encodeURIComponent(selectedId)}`, { signal: control.signal }) : Promise.resolve(null)).then(value => { if (active && generation === sequence.current) setDetail(value); return value; }),
      ]);
      if (generation !== sequence.current) return;
      setSession(nextSession); setWorkspace(nextWorkspace); setDetail(nextDetail); setAuthLost(false); setError("");
    } catch (failure) { active = false; control.abort(); if (generation === sequence.current) {
      setError((failure as Error).message);
      const denied = failure instanceof APIError && [401, 403].includes(failure.status);
      if (denied) { setWorkspace(null); setDetail(null); requests.current.clear(); dirty.current = false; }
      else if (failure instanceof APIError && failure.status === 404) setDetail(null);
      setAuthLost(denied);
    } }
    finally { if (refreshController.current === control) refreshController.current = null; if (generation === sequence.current) setRefreshing(false); }
  }, [selectedId]);
  const invalidateRefresh = useCallback(() => { sequence.current++; refreshController.current?.abort(); }, []);
  // Network responses update this external server snapshot; no derived state is recomputed here.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void refresh(); return invalidateRefresh; }, [refresh, invalidateRefresh]);
  const navigate = useCallback((url: string) => { if (dirty.current && !window.confirm("当前资料尚未保存。离开并放弃这些修改？")) return; dirty.current = false; setDrawer(false); router.push(url); }, [router]);
  const setUnsaved = useCallback((value: boolean) => { dirty.current = value; }, []);
  function guardLink(event: MouseEvent<HTMLDivElement>) {
    if (!dirty.current || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !["http:", "https:"].includes(target.protocol)) return;
    if (target.pathname === window.location.pathname && target.search === window.location.search) return;
    event.preventDefault(); event.stopPropagation(); navigate(`${target.pathname}${target.search}${target.hash}`);
  }
  const select = useCallback((id: string | null) => navigate(id ? `/publishing?manuscript=${encodeURIComponent(id)}` : "/publishing"), [navigate]);
  const mutate = useCallback(async <T,>(path: string, data: object, method: "POST" | "PATCH" = "POST"): Promise<T> => {
    if (!session) throw new APIError(401, "请先登录。");
    const fingerprint = `${method}:${path}:${JSON.stringify(data)}`;
    const requestID = requests.current.get(fingerprint) ?? newRequestId(); requests.current.set(fingerprint, requestID);
    try {
      const result = await fetchJSON<T>(path, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ ...data, request_id: requestID }) });
      requests.current.delete(fingerprint); return result;
    } catch (failure) { if (failure instanceof APIError && failure.status === 401) setAuthLost(true); throw failure; }
  }, [session]);
  async function createDraft() { setError(""); setRefreshing(true); try { const result = await mutate<{ manuscript_id: string }>("/drafts", {}); select(result.manuscript_id); await refresh(); } catch (failure) { setError((failure as Error).message); } finally { setRefreshing(false); } }
  if (!session || authLost) return <div className={styles.loading}><h1>Pivot</h1><p role="status">{error || "正在载入工作区…"}</p>{authLost ? <Link href="/">返回登录</Link> : <button onClick={() => void refresh()} disabled={refreshing}>重新载入</button>}</div>;
  return <Context.Provider value={{ session, workspace, detail, selectedId, error, refreshing, refresh, select, setReviewContext, setUnsaved, mutate }}>
    <div className={styles.shell} data-theme={theme} onClickCapture={guardLink}>
      <a className={styles.skip} href="#publishing-chat">跳到对话</a>
      <aside className={`${styles.sidebar} ${drawer ? styles.drawerOpen : ""}`} aria-label="我的工作">
        <div className={styles.brand}><strong>Pivot</strong><button className={styles.mobileOnly} onClick={() => setDrawer(false)} aria-label="关闭工作列表"><Glyph name="close" /></button></div>
        <p className={styles.journal}>{session.journal.name}</p>
        <div className={styles.sidebarActions}>{["editor", "chief_editor"].includes(session.user.role) && <Link href="/library"><Glyph name="file" size={16} />内部审阅资料</Link>}<button onClick={() => select(null)}>我的工作 <span>{workspace?.counts.actionable ?? 0}</span></button>{session.user.role === "author" && <button onClick={() => void createDraft()} disabled={refreshing}><Glyph name="file" size={16} />新建投稿</button>}</div>
        <div className={styles.taskList}>{workspace?.tasks.length ? workspace.tasks.map(task => <Link key={task.id} href={`/publishing?manuscript=${task.manuscript_id}`} onClick={event => { event.preventDefault(); select(task.manuscript_id); }} className={selectedId === task.manuscript_id ? styles.selected : ""}><strong>{task.label}</strong><span>{task.title || "未命名投稿"}</span><small>{task.number}{task.status === "waiting" ? " · 等待处理" : task.blocking ? " · 需要你处理" : ""}</small></Link>) : <p className={styles.emptySmall}>目前没有分派给你的待办。</p>}</div>
        <div className={styles.userArea}><strong>{session.user.name}</strong><span>{roleLabels[session.user.role] ?? session.user.role}</span><div className={styles.appearance}><label htmlFor="publishing-theme">外观</label><select id="publishing-theme" name="theme" value={theme} onChange={event => { memoryTheme = event.target.value; writeStorage("localStorage", "publishing-theme", memoryTheme); window.dispatchEvent(new Event("publishing-theme-change")); }}><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div><Link href="/">账号与设置</Link></div>
      </aside>
      <section className={styles.center} aria-label="出版助手"><header className={styles.topbar}><button className={styles.mobileOnly} aria-label="打开工作列表" onClick={() => setDrawer(value => !value)}><Glyph name="inbox" /></button><span>出版助手</span><span className={styles.model}>{session.model.provider === "mock" ? "Mock · 模拟模型" : `${session.model.provider} · ${session.model.model ?? ""}`}{session.model.available === false ? " · 未就绪" : ""}</span></header><Conversation key={`${session.journal.id}:${session.user.id}:${session.user.role}:${session.csrf_token}`} navigate={navigate} /></section>
      <main className={styles.material} aria-label="稿件材料">{error && <div role="alert" className={styles.error}>{error}<button onClick={() => void refresh()} disabled={refreshing}>重新载入</button></div>}{children}</main>
    </div>
  </Context.Provider>;
}

function Conversation({ navigate }: { navigate: (url: string) => void }) {
  const { session, selectedId, detail, refresh } = usePublishing();
  const pathname = usePathname(); const cacheKey = `publishing-chat-input:${session.journal.id}:${session.user.id}:${session.user.role}`;
  const contextKey = JSON.stringify([session.journal.id, session.user.id, session.user.role, selectedId ?? "journal"]);
  const [transcript, setTranscript] = useState<{ key: string; messages: ChatMessage[]; loaded: boolean; error: string; historyError: string; historyLoading: boolean }>({ key: contextKey, messages: [], loaded: false, error: "", historyError: "", historyLoading: true });
  const [input, setInput] = useState(() => typeof window === "undefined" ? "" : readStorage("sessionStorage", cacheKey) ?? "");
  const [busy, setBusy] = useState(false);
  const pending = useRef<{ scopeKey: string; request_id: string; message: string; context: { manuscript_id: string | null; version_id: string | null; scope: string; view: string } } | null>(null);
  const bottom = useRef<HTMLDivElement>(null); const composing = useRef(false); const historySequence = useRef(0);
  const historyController = useRef<AbortController | null>(null);
  const inFlightHistory = useRef<{ generation: number; key: string; messages: ChatMessage[] } | null>(null);
  const permissionEpoch = useRef(new Map<string, number>());
  // Derive the visible transcript by context immediately, before a history response arrives.
  const messages = transcript.key === contextKey ? transcript.messages : EMPTY_MESSAGES;
  const error = transcript.key === contextKey ? transcript.error : "";
  const loaded = transcript.key === contextKey && transcript.loaded;
  const historyError = transcript.key === contextKey ? transcript.historyError : "";
  const load = useCallback(async () => {
    historyController.current?.abort();
    const control = new AbortController(); historyController.current = control;
    const generation = ++historySequence.current;
    const authorizedAtStart = permissionEpoch.current.get(contextKey) ?? 0;
    inFlightHistory.current = { generation, key: contextKey, messages: [] };
    setTranscript(previous => previous.key === contextKey ? { ...previous, historyError: "", historyLoading: true } : { key: contextKey, messages: [], loaded: false, error: "", historyError: "", historyLoading: true });
    try {
      const result = await fetchJSON<{ messages: ChatMessage[] }>(selectedId ? `/chat?manuscript_id=${encodeURIComponent(selectedId)}` : "/chat", { signal: control.signal });
      if (generation !== historySequence.current) return;
      if (authorizedAtStart !== (permissionEpoch.current.get(contextKey) ?? 0)) {
        setTranscript(previous => previous.key === contextKey ? { ...previous, loaded: true, historyLoading: false } : previous); return;
      }
      // The server determines authorized history and ordering. Only append POST
      // responses received during this GET, never resurrect an older local history.
      const fresh = inFlightHistory.current?.generation === generation ? inFlightHistory.current.messages : [];
      setTranscript(previous => previous.key === contextKey ? { ...previous, messages: mergeMessages(result.messages, fresh), loaded: true, historyError: "", historyLoading: false } : previous);
    } catch (failure) {
      if (control.signal.aborted) return;
      const denied = failure instanceof APIError && [401, 403, 404].includes(failure.status);
      if (generation === historySequence.current) {
        if (denied) permissionEpoch.current.set(contextKey, (permissionEpoch.current.get(contextKey) ?? 0) + 1);
        setTranscript(previous => previous.key === contextKey ? { ...previous, messages: denied ? [] : previous.messages, loaded: true, historyError: (failure as Error).message, historyLoading: false } : previous);
      }
    } finally {
      if (historyController.current === control) historyController.current = null;
      if (inFlightHistory.current?.generation === generation) inFlightHistory.current = null;
    }
  }, [selectedId, contextKey]);
  // Restore only the selected manuscript's persisted transcript, or the journal transcript.
  useEffect(() => { void load(); return () => { historySequence.current += 1; historyController.current?.abort(); inFlightHistory.current = null; }; }, [load]);
  // The always-mounted composer preserves its unsent per-user draft across route changes.
  useEffect(() => { writeStorage("sessionStorage", cacheKey, input); }, [input, cacheKey]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);
  async function send(retry = false) {
    if (busy || (!retry && !input.trim())) return;
    const context = { manuscript_id: selectedId, version_id: detail?.id === selectedId ? detail.version?.id ?? detail.accepted_version_id ?? null : null, scope: selectedId ? "case" : "journal", view: pathname.includes("/preview/") ? "preview" : pathname.includes("/review/") ? "review" : detail?.can_edit_intake ? "intake" : "work" };
    if (!pending.current || pending.current.scopeKey !== contextKey || (!retry && (pending.current.message !== input.trim() || JSON.stringify(pending.current.context) !== JSON.stringify(context)))) pending.current = { scopeKey: contextKey, request_id: newRequestId(), message: input.trim(), context };
    const request = pending.current; const requestKey = request.scopeKey;
    const authorizedAtStart = permissionEpoch.current.get(requestKey) ?? 0;
    setBusy(true);
    setTranscript(previous => previous.key === requestKey ? { ...previous, error: "" } : { key: requestKey, messages: [], loaded: false, error: "", historyError: "", historyLoading: true });
    try {
      const result = await fetchJSON<{ messages: ChatMessage[]; state_changed: boolean }>("/chat", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ request_id: request.request_id, message: request.message, context: request.context }) });
      const stillAuthorized = authorizedAtStart === (permissionEpoch.current.get(requestKey) ?? 0);
      if (stillAuthorized && inFlightHistory.current?.key === requestKey) inFlightHistory.current.messages = mergeMessages(inFlightHistory.current.messages, result.messages);
      // A late response from another manuscript must never enter the current transcript.
      setTranscript(previous => {
        if (!stillAuthorized || previous.key !== requestKey) return previous;
        return { ...previous, messages: mergeMessages(previous.messages, result.messages) };
      });
      setInput(value => value.trim() === request.message ? "" : value); if (pending.current === request) pending.current = null; if (result.state_changed) await refresh();
    } catch (failure) {
      const denied = failure instanceof APIError && [401, 403, 404].includes(failure.status);
      if (denied) permissionEpoch.current.set(requestKey, (permissionEpoch.current.get(requestKey) ?? 0) + 1);
      setTranscript(previous => previous.key === requestKey ? denied ? { ...previous, messages: [], loaded: true, error: "", historyError: (failure as Error).message } : { ...previous, error: (failure as Error).message } : previous);
    } finally { setBusy(false); }
  }
  return <><div className={styles.chatContext}>{detail?.id === selectedId ? `${detail.number} · ${detail.stage_label}` : "期刊工作区"}<span>仅限合成或公开授权测试资料 · 邮件发送已禁用</span></div><div id="publishing-chat" className={styles.transcript} tabIndex={-1}>
    {!loaded && <p role="status" className={styles.subtle}>正在载入当前对话…</p>}{loaded && !messages.length && <div className={styles.chatEmpty}><h1>今天需要推进什么？</h1><p>告诉我你的目标，或先从左侧选择待办。你也可以先把投稿信息交给我整理。</p></div>}
    {messages.map(message => <article key={message.id} className={message.role === "user" ? styles.userMessage : styles.assistantMessage}>{message.revision_comparison ? <RevisionComparisonPanel scopeKey={`${session.journal.id}:${session.user.id}:${session.user.role}`} disabled={busy} report={message.revision_comparison} onContinue={prompt => { if (busy) return; const next = input.trim() ? `${input}\n\n${prompt}` : prompt; if (next.length <= 8000) { setInput(next); document.getElementById("publishing-message")?.focus(); } else { setTranscript(previous => ({...previous, error:"输入已较长，请先发送或清理草稿后再继续。"})); } }} current={detail?.id === selectedId ? { versionId: detail.version?.id ?? detail.accepted_version_id ?? null, revision: detail.revision, versions: detail.versions } : undefined} /> : <div className={styles.messageText}>{message.content}</div>}{message.role === "assistant" && <small>{message.provider === "mock" ? "Mock · 模拟结果" : message.provider}</small>}{message.references?.map((reference, index) => <div className={styles.reference} key={`${reference.manuscript_id}-${index}`}><Link href={`/publishing?manuscript=${reference.manuscript_id}`} onClick={event => { event.preventDefault(); navigate(`/publishing?manuscript=${reference.manuscript_id}`); }}>{reference.label}</Link>{reference.quote && <blockquote>{reference.quote}</blockquote>}</div>)}{message.tool_receipts?.length > 0 && <details className={styles.receipts}><summary>工具执行记录 · {message.tool_receipts.length}</summary>{message.tool_receipts.map((receipt, index) => <div key={index}>{receipt.tool} · {receipt.status}</div>)}</details>}{message.action && <Link className={styles.actionLink} href={message.action.type === "review" ? `/publishing/review/${message.action.proposal_id}` : `/publishing?manuscript=${message.action.manuscript_id}`} onClick={event => { event.preventDefault(); if (message.action) navigate(message.action.type === "review" ? `/publishing/review/${message.action.proposal_id}` : `/publishing?manuscript=${message.action.manuscript_id}`); }}>{message.action.type === "review" ? "打开负责人审核" : "查看稿件"}</Link>}</article>)}
    {busy && <p className={styles.subtle} role="status">正在理解并执行允许的工具…</p>}<div ref={bottom} />
  </div><div className={styles.composerArea}>{historyError && <div className={styles.error} role="alert">对话历史未载入：{historyError}<button disabled={transcript.historyLoading} onClick={() => void load()}>重新载入历史</button></div>}{error && <div className={styles.error} role="alert">{error}<button disabled={busy} onClick={() => void send(true)}>重试</button></div>}<NextSteps key={`${contextKey}:${detail?.revision}:${messages.at(-1)?.id}`} url={selectedId ? `/api/publishing/manuscripts/${selectedId}/guidance` : '/api/publishing/guidance'} objectId={selectedId} versionId={detail?.id === selectedId ? detail.version?.id ?? null : null} revision={detail?.id === selectedId ? detail.revision : null} role={session.user.role} disabled={busy} onChoose={prompt => { const next = input.trim() ? `${input}\n\n${prompt}` : prompt; if (next.length > 8000) { setTranscript(previous => ({...previous, error: "输入已较长，请先发送或清理当前草稿，再选择建议。"})); return; } setInput(next); document.getElementById('publishing-message')?.focus(); }} /><form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}><label className={styles.srOnly} htmlFor="publishing-message">向出版助手发送消息</label><textarea id="publishing-message" name="message" autoComplete="off" rows={2} maxLength={8000} placeholder="描述目标，或粘贴你的投稿信息…" value={input} onChange={event => setInput(event.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current && event.keyCode !== 229) { event.preventDefault(); void send(); } }} /><div className={styles.composerFooter}><span>Enter 发送 · Shift+Enter 换行</span><button type="submit" disabled={busy || !input.trim()} aria-label="发送消息"><Glyph name="arrow" size={18} />{busy ? "处理中…" : "发送"}</button></div></form></div></>;
}
