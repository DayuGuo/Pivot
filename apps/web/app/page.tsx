"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

type User = { id: string; email: string; name: string; role: string };
type Session = { user: User; csrf_token: string };
type Manuscript = {
  id: string; title: string; status: string; created_at: string;
  author_name: string; editor_name: string;
  task: { id: string; status: string; kind: string } | null;
};
type Message = { id: string; role: string; content: string; provider: string; manuscript_id: string | null; created_at: string };
type Audit = { id: string; action: string; actor_name: string; entity_id: string; details: Record<string, unknown>; created_at: string };
type Workspace = { journal: { id: string; name: string }; manuscripts: Manuscript[]; messages: Message[]; audit: Audit[]; email_send_enabled: boolean };
const prompt = "创建一篇测试稿件，并交给编辑初筛。";
const roles: Record<string, string> = { editor: "编辑", chief_editor: "主编", author: "作者", reviewer: "审稿人" };
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
    close: <path d="m6 6 12 12M6 18 18 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}
function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? "brand-small" : ""}`} translate="no"><span className="brand-mark" aria-hidden="true">P</span><span>Publishing OS</span></div>;
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
  const [session, setSession] = useState<Session | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("editor@publishing.test");
  const [password, setPassword] = useState("EditorDemo2026!");
  const [message, setMessage] = useState("");
  const [view, setView] = useState<"chat" | "manuscripts" | "audit">("chat");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsVisible, setDetailsVisible] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pendingRequest = useRef<{ message: string; id: string } | null>(null);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const restored = await api<Session>("/auth/me");
        const data = await api<Workspace>("/workspace");
        if (active) { setSession(restored); setWorkspace(data); }
      } catch { /* No active session: show login. */ }
      finally { if (active) setLoading(false); }
    }
    void restore();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const narrow = window.matchMedia("(max-width: 700px)");
    const adaptPane = () => setDetailsVisible(!narrow.matches);
    adaptPane();
    narrow.addEventListener("change", adaptPane);
    return () => narrow.removeEventListener("change", adaptPane);
  }, []);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "instant", block: "end" }); }, [workspace?.messages.length, busy]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const nextSession = await api<Session>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const data = await api<Workspace>("/workspace");
      setSession(nextSession); setWorkspace(data); setPassword("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败，请重试"); }
    finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError("");
    try { setWorkspace(await api<Workspace>("/workspace")); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "更新失败"); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError("");
    try {
      await api("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session!.csrf_token } });
      setSession(null); setWorkspace(null); setSelectedId(null); setView("chat"); pendingRequest.current = null;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "退出失败"); }
    finally { setBusy(false); }
  }
  async function send(text = message) {
    if (!text.trim() || !session || busy) return;
    setBusy(true); setError("");
    if (!pendingRequest.current || pendingRequest.current.message !== text.trim()) pendingRequest.current = { message: text.trim(), id: crypto.randomUUID() };
    try {
      const result = await api<{ manuscript: Manuscript | null }>("/conversations/commands", {
        method: "POST", headers: { "X-CSRF-Token": session.csrf_token },
        body: JSON.stringify({ message: text.trim(), request_id: pendingRequest.current.id }),
      });
      pendingRequest.current = null;
      setMessage("");
      setWorkspace(await api<Workspace>("/workspace"));
      if (result.manuscript) { setSelectedId(result.manuscript.id); setDetailsVisible(true); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "执行失败，可以重试"); }
    finally { setBusy(false); }
  }
  async function openManuscript(id: string) {
    setError("");
    try { await api<Manuscript>(`/manuscripts/${id}`); setSelectedId(id); setDetailsVisible(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "无法读取稿件"); }
  }

  if (loading) return <main className="loading-screen"><Brand /><span className="loader"/><p>正在恢复工作台…</p></main>;
  if (!session || !workspace) return <main className="login-screen">
    <div className="login-story"><Brand /><div><h1>出版工作，<br/><span>从对话开始。</span></h1></div></div>
    <section className="login-panel"><div className="login-form-wrap"><h2>欢迎回到工作台</h2><form onSubmit={login}><label htmlFor="email">邮箱</label><input id="email" name="email" spellCheck={false} autoComplete="username" type="email" required value={email} onChange={e => setEmail(e.target.value)} /><label htmlFor="password">密码</label><input id="password" name="password" autoComplete="current-password" type="password" required value={password} onChange={e => setPassword(e.target.value)} />{error && <div role="alert" ref={errorRef} tabIndex={-1} className="error">{error}</div>}<button className="primary login-button" disabled={busy}>{busy ? "正在登录…" : "进入工作台"}<Icon name="chevron"/></button></form><div className="demo-account"><span>本地演示账号</span><button type="button" onClick={() => { setEmail("editor@publishing.test"); setPassword("EditorDemo2026!"); }}>编辑</button><button type="button" onClick={() => { setEmail("author@publishing.test"); setPassword("AuthorDemo2026!"); }}>作者</button><button type="button" onClick={() => { setEmail("reviewer@publishing.test"); setPassword("ReviewerDemo2026!"); }}>审稿人</button></div><p className="login-safety"><Icon name="lock" size={14}/>仅使用合成测试数据 · 真实邮件发送已禁用</p></div></section>
  </main>;

  const canCreate = ["editor", "chief_editor"].includes(session.user.role);
  const selected = workspace.manuscripts.find(item => item.id === selectedId) || null;
  const selectedAudit = selected ? workspace.audit.filter(item => item.entity_id === selected.id || JSON.stringify(item.details).includes(selected.id)) : [];
  const titles = { chat: "编辑助手", manuscripts: "稿件管理", audit: "审计记录" };
  return <div className="app-shell"><a className="skip-link" href="#workspace-main">跳转到工作区</a>
    <aside className="sidebar"><Brand small/><div className="journal-switch"><span className="journal-avatar">J</span><div><strong>{workspace.journal.name}</strong></div></div><nav aria-label="工作空间"><button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}><Icon name="chat"/>编辑助手</button><button className={view === "manuscripts" ? "active" : ""} onClick={() => setView("manuscripts")}><Icon name="file"/>稿件管理<span className="nav-count">{workspace.manuscripts.length}</span></button><button className={view === "audit" ? "active" : ""} onClick={() => setView("audit")}><Icon name="activity"/>审计记录</button></nav><div className="user-area"><div className="user-avatar">{session.user.name.slice(0, 1)}</div><div className="user-info"><strong>{session.user.name}</strong><span>{roles[session.user.role] || session.user.role}</span></div><button className="icon-button" aria-label="退出登录" onClick={logout} disabled={busy}><Icon name="logout" size={17}/></button></div></aside>
    <main className="workspace" id="workspace-main" tabIndex={-1}><header className="workspace-header"><div className="breadcrumb"><h1>{titles[view]}</h1></div><div className="header-actions"><span className="environment-badge">本地原型</span><button className="icon-button" aria-label={detailsVisible ? "隐藏稿件面板" : "显示稿件面板"} aria-pressed={detailsVisible} onClick={() => setDetailsVisible(!detailsVisible)}><Icon name="file" size={16}/></button><button className="icon-button" aria-label="刷新工作台" onClick={refresh} disabled={busy}><Icon name="refresh" size={16}/></button></div></header>
      {error && <div role="alert" ref={errorRef} tabIndex={-1} className="error workspace-error">{error}<button aria-label="关闭错误提示" onClick={() => setError("")}><Icon name="close" size={15}/></button></div>}
      <div className="workspace-content"><section className={`main-panel ${view !== "chat" ? "list-panel" : ""}`}>
        {view === "chat" ? <><div className="conversation-heading"><div><span className="assistant-symbol"><Icon name="spark" size={17}/></span><span className="provider-badge">Mock · 模拟模型</span></div></div><div className="conversation-scroll" aria-label="对话记录">
          {workspace.messages.length === 0 ? <div className="welcome"><div className="welcome-wordmark" translate="no">Publishing OS</div><h2>让研究，从这里向前。</h2><button className="starter-card" onClick={() => void send(prompt)} disabled={busy || !canCreate}><span className="starter-icon"><Icon name="file" size={21}/></span><span><strong>创建测试稿件</strong></span><Icon name="chevron" size={18}/></button></div> : <div className="messages" role="log" aria-live="polite" aria-relevant="additions">{workspace.messages.map(item => <article key={item.id} className={`message ${item.role === "user" ? "message-user" : "message-assistant"}`}><div className="message-avatar">{item.role === "user" ? session.user.name.slice(0, 1) : <Icon name="spark" size={16}/>}</div><div className="message-body"><div className="message-meta"><strong>{item.role === "user" ? "你" : "编辑助手"}</strong><time>{date(item.created_at)}</time></div><div className="message-text">{item.content}</div>{item.manuscript_id && <button className="result-card" onClick={() => void openManuscript(item.manuscript_id!)}><span className="result-icon"><Icon name="check" size={19}/></span><span><strong>查看稿件与初筛任务</strong><small>#{shortId(item.manuscript_id)}</small></span><Icon name="chevron" size={17}/></button>}</div></article>)}</div>}
          {busy && <div className="thinking" role="status"><span className="loader"/>正在处理请求…</div>}<div ref={endRef}/></div><div className="composer-area"><form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}><textarea name="command" autoComplete="off" aria-label="对话指令" placeholder={canCreate ? "告诉我你想完成的编辑工作…" : "当前角色可查看工作台，创建与分派需要编辑权限"} value={message} disabled={busy} rows={2} maxLength={2000} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }}/><div className="composer-bottom"><span><Icon name="lock" size={12}/>受权限策略保护</span><button type="submit" className="send-button" aria-label="发送指令" disabled={busy || !message.trim()}><Icon name="arrow" size={18}/></button></div></form></div></> : view === "manuscripts" ? <><div className="list-heading"><h2>稿件管理 <span>{workspace.manuscripts.length}</span></h2></div><div className="manuscript-list">{workspace.manuscripts.length ? workspace.manuscripts.map(item => <button key={item.id} className={`manuscript-row ${selectedId === item.id ? "selected" : ""}`} onClick={() => void openManuscript(item.id)}><span className="file-box"><Icon name="file" size={20}/></span><span className="manuscript-row-title"><strong>{item.title}</strong><small>#{shortId(item.id)} · {item.author_name} · {date(item.created_at)}</small></span><Status value={item.status}/><Icon name="chevron" size={16}/></button>) : <div className="empty-state"><Icon name="file" size={30}/><h2>暂无可查看的稿件</h2><p>{canCreate ? "在编辑助手中创建第一篇测试稿件。" : "稿件会根据角色和归属关系显示在这里。"}</p>{canCreate && <button className="secondary" onClick={() => setView("chat")}>前往编辑助手</button>}</div>}</div></> : <><div className="list-heading"><h2>审计记录 <span>{workspace.audit.length}</span></h2></div><div className="audit-list" data-testid="audit-list">{workspace.audit.length ? workspace.audit.map(item => <div className="audit-row" key={item.id}><span className="audit-point"/><div><strong>{item.action}</strong><p>{item.actor_name} <span>· {date(item.created_at)}</span></p>{item.entity_id && <small>#{shortId(item.entity_id)}</small>}</div></div>) : <div className="empty-state"><Icon name="activity" size={30}/><h2>暂无审计记录</h2></div>}</div></>}
      </section>
      {detailsVisible && <aside className="detail-panel" aria-label="稿件详情"><div className="detail-header"><strong>{selected ? "稿件详情" : "工作台概览"}</strong>{selected && <button className="icon-button" aria-label="关闭稿件详情" onClick={() => setDetailsVisible(false)}><Icon name="close" size={16}/></button>}</div>{selected ? <div className="detail-body" data-testid="manuscript-detail"><span className="manuscript-id">#{shortId(selected.id)}</span><h2>{selected.title}</h2><Status value={selected.status}/><div className="detail-properties"><div><span>作者</span><strong>{selected.author_name}</strong></div><div><span>负责编辑</span><strong>{selected.editor_name || "待分派"}</strong></div><div><span>创建时间</span><strong>{date(selected.created_at)}</strong></div><div><span>数据类型</span><strong>合成测试稿件</strong></div></div><div className="detail-section-title">工作流进展</div><div className="workflow-steps"><div className="step done"><span><Icon name="check" size={12}/></span><div><strong>稿件创建</strong></div></div><div className="step done"><span><Icon name="check" size={12}/></span><div><strong>提交完成</strong></div></div><div className="step current"><span/><div><strong>编辑初筛</strong><small>{selected.task ? `${statuses[selected.task.status] || selected.task.status} · ${selected.editor_name}` : "等待编辑任务"}</small></div></div></div>{selected.task && <div className="task-box"><Icon name="file" size={16}/><div><strong>编辑初筛任务</strong><small>#{shortId(selected.task.id)}</small></div><span>{statuses[selected.task.status] || selected.task.status}</span></div>}<div className="detail-section-title">相关审计 <span>{selectedAudit.length}</span></div><div className="detail-audit">{selectedAudit.length ? selectedAudit.map(item => <div key={item.id}><span className="audit-point"/><div><strong>{item.action}</strong><small>{item.actor_name} · {date(item.created_at)}</small></div></div>) : <p className="muted">暂无记录</p>}</div></div> : <div className="detail-body"><div className="overview-stat"><span>可查看的稿件</span><strong>{workspace.manuscripts.length}<small>篇</small></strong></div><div className="detail-section-title">最近稿件</div>{workspace.manuscripts.slice(0, 5).map(item => <button className="recent-manuscript" key={item.id} onClick={() => void openManuscript(item.id)}><Icon name="file" size={17}/><span><strong>{item.title}</strong><small>{statuses[item.status] || item.status}</small></span><Icon name="chevron" size={14}/></button>)}{!workspace.manuscripts.length && <p className="overview-empty">暂无稿件</p>}</div>}<div className="email-guard"><span className="guard-dot"/><span>真实邮件发送已禁用</span><Icon name="lock" size={12}/></div></aside>}</div>
    </main>
  </div>;
}
