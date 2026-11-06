"use client";
import IdentityControl from "../components/identity/control";
import GlobalSearch from "../components/search/global-search";
import { requestId as newRequestId } from "../components/browser";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { SettingsButton } from "../components/settings/panel";

type User = { id: string; email: string; name: string; role: string };
type Session = { user: User; csrf_token: string };
type Manuscript = {
  id: string; title: string; status: string; created_at: string;
  author_name: string; editor_name: string;
  task: { id: string; status: string; kind: string } | null;
};
type Message = { id: string; role: string; content: string; provider: string; manuscript_id: string | null; created_at: string };
type Audit = { id: string; action: string; actor_name: string; entity_id: string; details: Record<string, unknown>; created_at: string };
type Conversation = { id: string; title: string; updated_at: string; message_count: number };
type Workspace = { conversations: Conversation[]; active_conversation_id: string | null; journal: { id: string; name: string }; manuscripts: Manuscript[]; messages: Message[]; audit: Audit[]; email_send_enabled: boolean };
const privatePreview = process.env.NEXT_PUBLIC_PIVOT_PRIVATE_PREVIEW === "true";
const prompt = "创建一篇测试稿件，并交给编辑初筛。";
const statuses: Record<string, string> = { draft: "草稿", submitted: "已投稿", screening: "编辑初筛", assigned: "已分派", pending: "待处理", open: "待处理" };

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    chat: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6A8.4 8.4 0 0 1 12.5 3h.5a8.5 8.5 0 0 1 8 8v.5Z"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h5"/></>,
    activity: <><path d="M3 12h4l3-8 4 16 3-8h4"/></>,
    arrow: <><path d="M12 19V5M5 12l7-7 7 7"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 7a7 7 0 0 1 11.6-2L20 8M4 16l2.3 3A7 7 0 0 0 18 17"/></>,
    spark: <><path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z"/></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}
function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? "brand-small" : ""}`} translate="no"><span>Pivot</span></div>;
}
function date(value: string) { return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function shortId(id: string) { return id.slice(0, 8).toUpperCase(); }
function Status({ value }: { value: string }) { return <span className="status"><span />{statuses[value] || value}</span>; }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    let detail = `请求失败 (${response.status})`;
    try { const body = await response.json(); detail = typeof body.detail === "string" ? body.detail : detail; } catch { /* preserve useful HTTP status */ }
    throw new Error(response.status === 403 ? `权限不足：${detail}` : detail);
  }
  return response.json();
}

export default function Home() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState(privatePreview ? "" : "editor@publishing.test");
  const [password, setPassword] = useState(privatePreview ? "" : "EditorDemo2026!");
  const [message, setMessage] = useState("");
  const [view, setView] = useState<"chat" | "manuscripts" | "audit">("chat");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const drawerRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pendingRequest = useRef<{ message: string; id: string; conversation: string | null } | null>(null);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const restored = await api<Session>("/auth/me");
        let data: Workspace;
        try { data = await api<Workspace>(workspacePath()); }
        catch (cause) {
          if (!new URLSearchParams(window.location.search).has("conversation")) throw cause;
          data = await api<Workspace>("/workspace");
          if (active) setError("无法打开此对话，已返回你的工作台。");
        }
        const manuscriptId = new URLSearchParams(window.location.search).get("manuscript");
        if (manuscriptId) {
          try {
            const item = await api<Manuscript>(`/manuscripts/${encodeURIComponent(manuscriptId)}`);
            data = { ...data, manuscripts: [item, ...data.manuscripts.filter(value => value.id !== item.id)] };
            if (active) { setSelectedId(item.id); setDetailsVisible(true); }
          } catch { if (active) setError("无法打开此稿件，已返回你的工作台。"); }
        }
        if (active) { setSession(restored); setWorkspace(data); rememberConversation(data.active_conversation_id, false); }
      } catch { /* No active session: show login. */ }
      finally { if (active) setLoading(false); }
    }
    void restore();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!drawerOpen) return;
    const menu = menuRef.current;
    drawerRef.current?.querySelector<HTMLButtonElement>(".mobile-close")?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setDrawerOpen(false); menuRef.current?.focus(); }
      if (event.key === "Tab") {
        const items = Array.from(drawerRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, a[href]') || []).filter(item => item.getClientRects().length > 0);
        if (!items?.length) return;
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); requestAnimationFrame(() => menu?.focus()); };
  }, [drawerOpen]);
  useEffect(() => {
    const adapt = () => { if (window.matchMedia("(max-width: 700px)").matches) setDetailsVisible(false); else setDrawerOpen(false); };
    window.addEventListener("resize", adapt);
    return () => window.removeEventListener("resize", adapt);
  }, []);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "auto", block: "end" }); }, [workspace?.messages.length, busy]);

  function workspacePath(id?: string | null) {
    const selected = id === undefined ? new URLSearchParams(window.location.search).get("conversation") : id;
    return selected ? `/workspace?conversation_id=${encodeURIComponent(selected)}` : "/workspace";
  }
  function rememberConversation(id: string | null, clearManuscript = true) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("conversation", id); else url.searchParams.delete("conversation");
    if (clearManuscript) url.searchParams.delete("manuscript");
    window.history.replaceState(null, "", url);
  }
  function navigate(next: typeof view) { setView(next); setDrawerOpen(false); }
  async function switchConversation(id: string) {
    if (busy) return;
    if (id === workspace?.active_conversation_id) { navigate("chat"); return; }
    const previousId = workspace?.active_conversation_id || null;
    rememberConversation(id);
    setBusy(true); setError("");
    try {
      const data = await api<Workspace>(workspacePath(id));
      setDrafts(current => ({ ...current, [workspace?.active_conversation_id || "new"]: message }));
      setMessage(drafts[id] || ""); setWorkspace(data);
      setSelectedId(null); setDetailsVisible(false); navigate("chat"); pendingRequest.current = null;
    } catch (cause) { rememberConversation(previousId); setError(cause instanceof Error ? cause.message : "无法打开对话"); }
    finally { setBusy(false); }
  }
  async function newConversation() {
    if (busy || !session) return;
    setBusy(true); setError("");
    try {
      const conversation = await api<Conversation>("/conversations", { method: "POST", headers: { "X-CSRF-Token": session.csrf_token }, body: "{}" });
      const data = await api<Workspace>(workspacePath(conversation.id));
      setDrafts(current => ({ ...current, [workspace?.active_conversation_id || "new"]: message }));
      setMessage(""); setWorkspace(data); rememberConversation(conversation.id);
      setSelectedId(null); setDetailsVisible(false); navigate("chat"); pendingRequest.current = null;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "无法创建对话"); }
    finally { setBusy(false); }
  }
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const nextSession = await api<Session>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const data = await api<Workspace>("/workspace");
      setSession(nextSession); setWorkspace(data); setPassword(""); rememberConversation(data.active_conversation_id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败，请重试"); }
    finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError("");
    try { setWorkspace(await api<Workspace>(workspacePath(workspace?.active_conversation_id))); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "更新失败"); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError("");
    try {
      await api("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session!.csrf_token } });
      setSession(null); setWorkspace(null); setSelectedId(null); setView("chat"); setDetailsVisible(false); setDrawerOpen(false); setDrafts({}); setMessage(""); rememberConversation(null); pendingRequest.current = null;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "退出失败"); }
    finally { setBusy(false); }
  }
  async function send(text = message) {
    if (!text.trim() || !session || busy) return;
    setBusy(true); setError("");
    if (!pendingRequest.current || pendingRequest.current.message !== text.trim() || pendingRequest.current.conversation !== workspace?.active_conversation_id) pendingRequest.current = { message: text.trim(), id: newRequestId(), conversation: workspace?.active_conversation_id || null };
    try {
      const result = await api<{ manuscript: Manuscript | null; conversation_id: string }>("/conversations/commands", {
        method: "POST", headers: { "X-CSRF-Token": session.csrf_token },
        body: JSON.stringify({ message: text.trim(), request_id: pendingRequest.current.id, conversation_id: workspace?.active_conversation_id || undefined }),
      });
      pendingRequest.current = null;
      setMessage(""); setDrafts(current => ({ ...current, [result.conversation_id]: "" }));
      setWorkspace(await api<Workspace>(workspacePath(result.conversation_id))); rememberConversation(result.conversation_id);
      if (result.manuscript) { setSelectedId(result.manuscript.id); setDetailsVisible(true); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "执行失败，可以重试"); }
    finally { setBusy(false); }
  }
  async function openManuscript(id: string) {
    setError("");
    try {
      const item = await api<Manuscript>(`/manuscripts/${encodeURIComponent(id)}`);
      setWorkspace(current => current ? { ...current, manuscripts: [item, ...current.manuscripts.filter(value => value.id !== item.id)] } : current);
      setSelectedId(id); setDetailsVisible(true);
      const url = new URL(window.location.href); url.searchParams.set("manuscript", id); window.history.replaceState(null, "", url);
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "无法读取稿件"); }
  }

  if (loading) return <main className="loading-screen"><Brand /><span className="loader"/><p>正在恢复工作台…</p></main>;
  if (!session || !workspace) return <main className="login-screen">
    <div className="login-story"><Brand /><p>编辑工作台</p></div>
    <section className="login-panel"><div className="login-form-wrap"><h2>欢迎回到工作台</h2><form onSubmit={login}><label htmlFor="email">邮箱</label><input id="email" name="email" spellCheck={false} autoComplete="username" type="email" required value={email} onChange={e => setEmail(e.target.value)} /><label htmlFor="password">密码</label><input id="password" name="password" autoComplete="current-password" type="password" required value={password} onChange={e => setPassword(e.target.value)} />{error && <div role="alert" ref={errorRef} tabIndex={-1} className="error">{error}</div>}<button className="primary login-button" disabled={busy}>{busy ? "正在登录…" : "进入工作台"}<Icon name="chevron"/></button></form>{!privatePreview && <div className="demo-account"><span>本地演示账号</span><button type="button" onClick={() => { setEmail("multi@publishing.test"); setPassword("MultiDemo2026!"); }}>多身份</button><button type="button" onClick={() => { setEmail("editor@publishing.test"); setPassword("EditorDemo2026!"); }}>编辑</button><button type="button" onClick={() => { setEmail("author@publishing.test"); setPassword("AuthorDemo2026!"); }}>作者</button><button type="button" onClick={() => { setEmail("reviewer@publishing.test"); setPassword("ReviewerDemo2026!"); }}>审稿人</button></div>}<p className="login-safety"><Icon name="lock" size={14}/>仅使用合成测试数据 · 真实邮件发送已禁用</p></div></section>
  </main>;

  const canCreate = ["editor", "chief_editor"].includes(session.user.role);
  const selected = workspace.manuscripts.find(item => item.id === selectedId) || null;
  const selectedAudit = selected ? workspace.audit.filter(item => item.entity_id === selected.id || JSON.stringify(item.details).includes(selected.id)) : [];
  const titles = { chat: workspace.conversations?.find(item => item.id === workspace.active_conversation_id)?.title || "编辑助手", manuscripts: "稿件管理", audit: "审计记录" };
  return <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${drawerOpen ? "drawer-open" : ""}`}><a className="skip-link" href="#workspace-main">跳转到工作区</a>
    {drawerOpen && <button className="drawer-backdrop" aria-label="关闭导航遮罩" tabIndex={-1} onClick={() => setDrawerOpen(false)}/>}
    <aside className="sidebar" ref={drawerRef} aria-label="侧栏" role={drawerOpen ? "dialog" : undefined} aria-modal={drawerOpen || undefined}><div className="sidebar-top"><Brand small/><button className="icon-button desktop-collapse" aria-label="收起侧栏" onClick={() => setSidebarCollapsed(true)}><Icon name="panel"/></button><button className="icon-button mobile-close" aria-label="关闭导航" onClick={() => setDrawerOpen(false)}><Icon name="close"/></button></div>
    <GlobalSearch scope={`${workspace.journal.id}:${session.user.id}:${session.user.role}:${session.csrf_token}`} onActivate={(item, event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      const target = new URL(item.href, window.location.href);
      if (target.pathname !== "/") return;
      event.preventDefault();
      if (busy) { setError("正在处理当前请求，请完成后再切换对话或稿件。"); return; }
      const conversation = target.searchParams.get("conversation"), manuscript = target.searchParams.get("manuscript");
      if (conversation) void switchConversation(conversation);
      else if (manuscript) { setDrawerOpen(false); void openManuscript(manuscript); }
    }} />
    <nav aria-label="工作空间">{canCreate && <button onClick={() => router.push("/library")}><Icon name="file"/>内部审阅资料</button>}<button onClick={() => router.push("/publishing")}><Icon name="file"/>出版工作台</button>{canCreate && <button onClick={() => router.push("/workbench")}><Icon name="file"/>我的工作<span className="nav-count">演示</span></button>}<button className={view === "chat" ? "active" : ""} onClick={() => navigate("chat")}><Icon name="chat"/>编辑助手</button><button className={view === "manuscripts" ? "active" : ""} onClick={() => navigate("manuscripts")}><Icon name="file"/>稿件管理<span className="nav-count">{workspace.manuscripts.length}</span></button><button className={view === "audit" ? "active" : ""} onClick={() => navigate("audit")}><Icon name="activity"/>审计记录</button></nav>
    <div className="sessions-toolbar"><button className="new-conversation" onClick={() => void newConversation()} disabled={busy}><Icon name="plus"/>新对话</button></div>
    <div className="conversation-list" aria-label="会话列表">{(workspace.conversations || []).map(item => <button key={item.id} data-conversation-id={item.id} className={view === "chat" && item.id === workspace.active_conversation_id ? "selected" : ""} aria-current={view === "chat" && item.id === workspace.active_conversation_id ? "true" : undefined} onClick={() => void switchConversation(item.id)} disabled={busy}><strong>{item.title}</strong><small>{item.message_count} 条消息<span>{date(item.updated_at)}</span></small></button>)}{!workspace.conversations?.length && <p className="session-empty">暂无对话</p>}</div>
    <div className="settings-entry"><SettingsButton onOpen={() => setDrawerOpen(false)} /></div><div className="user-area"><IdentityControl user={session.user} /><button className="icon-button" aria-label="退出登录" onClick={logout} disabled={busy}><Icon name="logout" size={17}/></button></div></aside>
    <main className="workspace" id="workspace-main" tabIndex={-1} inert={drawerOpen}><header className="workspace-header"><div className="breadcrumb"><button ref={menuRef} className="icon-button sidebar-toggle" aria-label="打开导航" aria-expanded={drawerOpen} onClick={() => { if (window.matchMedia("(max-width: 700px)").matches) setDrawerOpen(true); else setSidebarCollapsed(false); }}><Icon name="panel"/></button><h1>{titles[view]}</h1></div><div className="header-actions"><button className="icon-button" aria-label={detailsVisible ? "隐藏稿件面板" : "显示稿件面板"} aria-pressed={detailsVisible} onClick={() => setDetailsVisible(!detailsVisible)}><Icon name="file" size={16}/></button><button className="icon-button" aria-label="刷新工作台" onClick={refresh} disabled={busy}><Icon name="refresh" size={16}/></button></div></header>
      {error && <div role="alert" ref={errorRef} tabIndex={-1} className="error workspace-error">{error}<button aria-label="关闭错误提示" onClick={() => setError("")}><Icon name="close" size={15}/></button></div>}
      <div className="workspace-content"><section className={`main-panel ${view !== "chat" ? "list-panel" : ""}`}>
        {view === "chat" ? <><div className="conversation-scroll" aria-label="对话记录">
          {workspace.messages.length === 0 ? <div className="welcome"><h2>开始编辑工作</h2><button className="starter-card" onClick={() => void send(prompt)} disabled={busy || !canCreate}><span className="starter-icon"><Icon name="file" size={21}/></span><span><strong>创建测试稿件</strong></span><Icon name="chevron" size={18}/></button></div> : <div className="messages" role="log" aria-live="polite" aria-relevant="additions">{workspace.messages.map(item => <article key={item.id} className={`message ${item.role === "user" ? "message-user" : "message-assistant"}`}><div className="message-body"><div className="message-meta"><strong>{item.role === "user" ? "你" : "编辑助手"}</strong><time>{date(item.created_at)}</time></div><div className="message-text">{item.content}</div>{item.manuscript_id && <button className="result-card" onClick={() => void openManuscript(item.manuscript_id!)}><span className="result-icon"><Icon name="check" size={19}/></span><span><strong>查看稿件与初筛任务</strong><small>#{shortId(item.manuscript_id)}</small></span><Icon name="chevron" size={17}/></button>}</div></article>)}</div>}
          {busy && <div className="thinking" role="status"><span className="loader"/>正在处理请求…</div>}<div ref={endRef}/></div><div className="composer-area"><form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}><textarea name="command" autoComplete="off" aria-label="对话指令" placeholder={canCreate ? "告诉我你想完成的编辑工作…" : "当前角色可查看工作台，创建与分派需要编辑权限"} value={message} disabled={busy} rows={2} maxLength={2000} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); void send(); } }}/><div className="composer-bottom"><span className="provider-badge">Mock · 模拟模型</span><button type="submit" className="send-button" aria-label="发送指令" disabled={busy || !message.trim()}><Icon name="arrow" size={18}/></button></div></form></div></> : view === "manuscripts" ? <><div className="list-heading"><h2>稿件管理 <span>{workspace.manuscripts.length}</span></h2></div><div className="manuscript-list">{workspace.manuscripts.length ? workspace.manuscripts.map(item => <button key={item.id} className={`manuscript-row ${selectedId === item.id ? "selected" : ""}`} onClick={() => void openManuscript(item.id)}><span className="file-box"><Icon name="file" size={20}/></span><span className="manuscript-row-title"><strong>{item.title}</strong><small>#{shortId(item.id)} · {item.author_name} · {date(item.created_at)}</small></span><Status value={item.status}/><Icon name="chevron" size={16}/></button>) : <div className="empty-state"><Icon name="file" size={30}/><h2>暂无可查看的稿件</h2><p>{canCreate ? "在编辑助手中创建第一篇测试稿件。" : "稿件会根据角色和归属关系显示在这里。"}</p>{canCreate && <button className="secondary" onClick={() => setView("chat")}>前往编辑助手</button>}</div>}</div></> : <><div className="list-heading"><h2>审计记录 <span>{workspace.audit.length}</span></h2></div><div className="audit-list" data-testid="audit-list">{workspace.audit.length ? workspace.audit.map(item => <div className="audit-row" key={item.id}><span className="audit-point"/><div><strong>{item.action}</strong><p>{item.actor_name} <span>· {date(item.created_at)}</span></p>{item.entity_id && <small>#{shortId(item.entity_id)}</small>}</div></div>) : <div className="empty-state"><Icon name="activity" size={30}/><h2>暂无审计记录</h2></div>}</div></>}
      </section>
      {detailsVisible && <aside className="detail-panel" aria-label="稿件详情"><div className="detail-header"><strong>{selected ? "稿件详情" : "工作台概览"}</strong><button className="icon-button" aria-label="关闭稿件详情" onClick={() => setDetailsVisible(false)}><Icon name="close" size={16}/></button></div>{selected ? <div className="detail-body" data-testid="manuscript-detail"><span className="manuscript-id">#{shortId(selected.id)}</span><h2>{selected.title}</h2><Status value={selected.status}/><div className="detail-properties"><div><span>作者</span><strong>{selected.author_name}</strong></div><div><span>负责编辑</span><strong>{selected.editor_name || "待分派"}</strong></div><div><span>创建时间</span><strong>{date(selected.created_at)}</strong></div><div><span>数据类型</span><strong>合成测试稿件</strong></div></div><div className="detail-section-title">工作流进展</div><div className="workflow-steps"><div className="step done"><span><Icon name="check" size={12}/></span><div><strong>稿件创建</strong></div></div><div className="step done"><span><Icon name="check" size={12}/></span><div><strong>提交完成</strong></div></div><div className="step current"><span/><div><strong>编辑初筛</strong><small>{selected.task ? `${statuses[selected.task.status] || selected.task.status} · ${selected.editor_name}` : "等待编辑任务"}</small></div></div></div>{selected.task && <div className="task-box"><Icon name="file" size={16}/><div><strong>编辑初筛任务</strong><small>#{shortId(selected.task.id)}</small></div><span>{statuses[selected.task.status] || selected.task.status}</span></div>}<div className="detail-section-title">相关审计 <span>{selectedAudit.length}</span></div><div className="detail-audit">{selectedAudit.length ? selectedAudit.map(item => <div key={item.id}><span className="audit-point"/><div><strong>{item.action}</strong><small>{item.actor_name} · {date(item.created_at)}</small></div></div>) : <p className="muted">暂无记录</p>}</div></div> : <div className="detail-body"><div className="overview-stat"><span>可查看的稿件</span><strong>{workspace.manuscripts.length}<small>篇</small></strong></div><div className="detail-section-title">最近稿件</div>{workspace.manuscripts.slice(0, 5).map(item => <button className="recent-manuscript" key={item.id} onClick={() => void openManuscript(item.id)}><Icon name="file" size={17}/><span><strong>{item.title}</strong><small>{statuses[item.status] || item.status}</small></span><Icon name="chevron" size={14}/></button>)}{!workspace.manuscripts.length && <p className="overview-empty">暂无稿件</p>}</div>}<div className="email-guard"><span className="guard-dot"/><span>真实邮件发送已禁用</span><Icon name="lock" size={12}/></div></aside>}</div>
    </main>
  </div>;
}
