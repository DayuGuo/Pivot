"use client";

import {useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent, type ReactNode} from "react";
import type {Case} from "./types";
import type {ChatAction, ChatContext, ChatHistory, ChatMessage, ChatReference, ChatScope, ChatTurn, ModelStatus} from "./chat-types";
import s from "./conversation.module.css";

type PendingTurn = {request_id: string; message: string; context: ChatContext};
type Props = {
  context: ChatContext;
  manuscript?: Case;
  manuscripts?: Case[];
  storageScope: string;
  csrf: string;
  onAction: (action: ChatAction) => void;
  onReference: (reference: ChatReference) => void;
  onStateChanged: () => Promise<void>;
  beforeSend?: (message: string, context: ChatContext) => Promise<void>;
  tools?: ReactNode;
  onScopeChange: (scope: ChatScope) => void;
};

const toolLabels: Record<string, string> = {inspect_manuscript:"读取稿件材料",list_tasks:"检索任务",open_material:"打开工作材料",prepare_invitation:"准备邀请草稿",open_decision_review:"打开负责人审核页"};
const statusLabels: Record<string, string> = {read:"已读取",material_opened:"已打开",human_review_required:"等待人工审核",staged_only:"已暂存，尚未保存",draft_saved:"草稿已保存，未发送",preserved_or_needs_selection:"已保留人工内容或等待选人"};
const scopeLabels: Record<ChatScope, string> = {case: "当前稿件", queue: "当前工作队列", journal: "本刊授权稿件"};
const viewLabels = {work: "查看工作列表", read: "打开稿件", reviewers: "查看审稿人与邀请草稿", revision: "查看修回与决定草稿"};

async function request<T>(options?: RequestInit, endpoint = "/api/editorial-demo/chat"): Promise<T> {
  const response = await fetch(endpoint, {credentials: "same-origin", cache: "no-store", ...options});
  if (!response.ok) {
    // Do not reflect server/proxy error bodies into a private conversation.
    throw new Error(response.status === 401 ? "登录已失效，请重新登录后重试。" : response.status === 403 ? "当前账号无法访问编辑对话，请检查登录状态后重试。" : response.status === 503 ? "真实模型尚未就绪或暂时不可用，请检查本地模型配置后重试。" : response.status === 422 ? "模型输出或工具校验未通过，未执行本次业务变更，请重试。" : "对话请求未完成，请重试。");
  }
  return response.json() as Promise<T>;
}

function actionHref(action: ChatAction): string {
  const params = new URLSearchParams(action.type === "navigate"
    ? {view: action.view, case: action.case_id}
    : {view: "work", stage: action.stage, query: action.query, today: String(action.today_only)});
  return `/workbench?${params}`;
}

function referenceHref(reference: ChatReference): string {
  const params = new URLSearchParams({view: "read", case: reference.case_id});
  if (reference.anchor) {
    params.set("version", reference.anchor.version);
    params.set("section", reference.anchor.section);
    params.set("quote", reference.anchor.quote);
    params.set("file", reference.anchor.file);
    params.set("location", reference.anchor.location);
  }
  return `/workbench?${params}`;
}

function intercept(event: MouseEvent<HTMLAnchorElement>, run: () => void) {
  if (event.button || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
  event.preventDefault();
  run();
}

function capturedScope(context: ChatContext, manuscripts: Case[]): string {
  return context.scope === "case" ? `${manuscripts.find(item => item.id === context.case_id)?.number || context.case_id} / ${context.version.toUpperCase()}` : scopeLabels[context.scope];
}

function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const ids = new Set(current.map(message => message.id));
  return [...current, ...incoming.filter(message => !ids.has(message.id))];
}

export default function Conversation(props: Props) {
  return <UserConversation key={props.storageScope} {...props}/>;
}

function UserConversation({context, manuscript, manuscripts = [], storageScope, csrf, onAction, onReference, onStateChanged, beforeSend, tools, onScopeChange}: Props) {
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [modelError, setModelError] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [sendError, setSendError] = useState("");
  const [refreshError, setRefreshError] = useState(false);
  const [newMessages, setNewMessages] = useState(false);
  const transcript = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const nearBottom = useRef(true);
  const sendingLock = useRef(false);
  const composing = useRef(false);
  const generation = useRef(0);
  const storageKey = `publishing-editorial-chat-${storageScope}`;
  const sourceCases = manuscript && !manuscripts.some(item => item.id === manuscript.id) ? [...manuscripts, manuscript] : manuscripts;
  const rounds = [...new Set((manuscript?.issues || []).filter(issue => [issue.before.version, issue.after.version].includes(context.version)).map(issue => issue.round))].sort((a, b) => a - b);
  const roundLabel = rounds.length ? `第${rounds.join("、")}轮` : manuscript?.rounds.length ? `第${manuscript.rounds.at(-1)?.number}轮` : "未开启外审";

  const checkModel = useCallback(async (signal?: AbortSignal) => {
    try {
      const status = await request<ModelStatus>({signal}, "/api/editorial-demo/chat/model");
      if (!signal?.aborted) { setModel(status); setModelError(false); }
    } catch { if (!signal?.aborted) setModelError(true); }
  }, []);

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setHistoryError("");
    try {
      const history = await request<ChatHistory>({signal});
      if (!signal?.aborted) { setMessages(history.messages); setNewMessages(!nearBottom.current); }
    } catch {
      if (!signal?.aborted) setHistoryError("对话记录未能加载，请重试。");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    generation.current += 1;
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || "{}") as {draft?: string; pending?: PendingTurn};
        if (typeof stored.draft === "string") setDraft(stored.draft.slice(0, 2000));
        const saved = stored.pending;
        if (saved && typeof saved.request_id === "string" && typeof saved.message === "string" && saved.context && ["case", "queue", "journal"].includes(saved.context.scope)) {
          setPending(saved);
          setDraft(saved.message);
          setSendError("上次消息尚未确认完成，请重试以恢复结果。");
        }
      } catch { /* Draft recovery is optional; the authenticated server owns history. */ }
      void loadHistory(controller.signal);
      void checkModel(controller.signal);
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [loadHistory, checkModel, storageKey]);

  const saveLocal = useCallback((text: string, turn: PendingTurn | null) => {
    try {
      if (text || turn) localStorage.setItem(storageKey, JSON.stringify({draft: text, pending: turn}));
      else localStorage.removeItem(storageKey);
    } catch { /* A blocked local cache must not prevent a server-backed conversation. */ }
  }, [storageKey]);

  useEffect(() => {
    const element = transcript.current;
    if (!element) return;
    if (nearBottom.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, pending, sending, loading]);

  const refreshState = async () => {
    try { await onStateChanged(); setRefreshError(false); }
    catch { setRefreshError(true); }
  };

  const send = async (text: string, retry?: PendingTurn) => {
    if (sendingLock.current || loading || historyError || !model?.available || modelError || (!retry && pending)) return;
    const message = text.trim();
    if (!message) { composer.current?.focus(); return; }
    const turn = retry || {request_id: crypto.randomUUID(), message, context: {...context}};
    const activeGeneration = generation.current;
    sendingLock.current = true;
    setSending(true);
    setPending(turn);
    setSendError("");
    if (!retry) setDraft(message);
    saveLocal(message, turn);
    let committed = false;
    try {
      if (beforeSend) await beforeSend(turn.message, turn.context);
      const result = await request<ChatTurn>({method: "POST", signal: AbortSignal.timeout(80000), headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf}, body: JSON.stringify(turn)});
      if (activeGeneration !== generation.current) return;
      committed = true;
      setMessages(current => mergeMessages(current, result.messages));
      setNewMessages(!nearBottom.current);
      setPending(null);
      setDraft("");
      saveLocal("", null);
      if (result.state_changed) await refreshState();
      if (activeGeneration !== generation.current) return;
      const action = result.messages.find(item => item.role === "assistant" && item.action)?.action;
      if (action) onAction(action);
    } catch (error) {
      if (activeGeneration === generation.current) {
        if (committed) setRefreshError(true);
        else setSendError(error instanceof Error && !["TypeError", "TimeoutError", "AbortError"].includes(error.name) ? error.message : "对话请求未完成，请重试。");
      }
    } finally {
      if (activeGeneration === generation.current) {
        sendingLock.current = false;
        setSending(false);
        if (committed) requestAnimationFrame(() => { if (activeGeneration === generation.current) composer.current?.focus({preventScroll: true}); });
      }
    }
  };

  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft); };
  const prompts = context.scope === "case"
    ? ["这篇稿件目前的状态和下一步是什么？", "列出当前版本尚未解决的问题，并给出原文依据。", "准备邀请草稿。", "协助准备决定草稿，先列出需要核验的事项。"]
    : ["列出今天需要处理的稿件。", "查找等待邀请审稿人的稿件。"];

  return <section className={s.conversation} aria-label="编辑对话">
    <header className={s.header}>
      <div className={s.heading}><h2>编辑对话</h2><span className={s.mock} role="status" aria-label="当前模型">{modelError ? "模型状态未知" : !model ? "检查模型…" : `${model.provider === "deepseek" ? "DeepSeek" : model.provider === "mock" ? "Mock" : "模型未配置"}${model.available ? "" : " · 未就绪"} · 合成数据`}</span></div>
      <select aria-label="对话范围" value={context.scope} onChange={event => onScopeChange(event.target.value as ChatScope)}>
        <option value="case">当前稿件与版本</option><option value="queue">当前工作队列</option><option value="journal">本刊授权稿件</option>
      </select>
    </header>
    <div className={s.currentContext} aria-label="当前对话上下文">
      {context.scope === "case" ? <><strong>{manuscript?.number || context.case_id}</strong><span>{context.version.toUpperCase()}</span><span>{roundLabel}</span>{manuscript && <span className={s.contextTitle}>{manuscript.title}</span>}</> : <><strong>{scopeLabels[context.scope]}</strong>{context.scope === "queue" && <span>{context.today_only ? "今天待办" : "全部期限"}{context.query ? ` / ${context.query}` : ""}</span>}</>}
    </div>
    <div className={s.transcript} ref={transcript} tabIndex={0} role="log" aria-label="对话记录" aria-live="polite" aria-busy={loading || sending} onScroll={event => {
      const element = event.currentTarget;
      nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 72;
      if (nearBottom.current) setNewMessages(false);
    }}>
      {loading && <p className={s.status} role="status">正在加载对话记录…</p>}
      {(modelError || (model && !model.available)) && <div className={s.error} role="alert"><p>模型尚未就绪。请通过本地安全启动入口配置新密钥，再检查配置；不会自动切换为 Mock。</p><button type="button" onClick={() => void checkModel()}>检查模型配置</button></div>}
      {historyError && <div className={s.error} role="alert"><p>{historyError}</p><button type="button" onClick={() => void loadHistory()}>重试加载</button></div>}
      {!loading && !historyError && !messages.length && !pending && <div className={s.empty}>
        <p>{context.scope === "case" ? "从当前稿件开始" : "整理接下来要处理的工作"}</p>
        <div className={s.prompts}>{prompts.map(prompt => <button type="button" key={prompt} onClick={() => void send(prompt)}>{prompt}</button>)}</div>
      </div>}
      {messages.map(message => <article key={message.id} className={message.role === "user" ? s.userMessage : s.assistantMessage} data-message-id={message.id}>
        <div className={s.messageMeta}><span>{message.role === "user" ? "你" : "编辑助手"}</span><span>{capturedScope(message.context, sourceCases)}</span>{message.role === "assistant" && <span>{message.provider === "deepseek" ? "DeepSeek · AI 建议" : "Mock"}</span>}</div>
        <p className={s.messageText}>{message.content}</p>
        {!!message.tool_receipts?.length && <details className={s.receipts}><summary>工具执行记录</summary><ol>{message.tool_receipts.map((receipt, index) => <li key={index}>{toolLabels[receipt.tool] || receipt.tool}：{statusLabels[receipt.status] || receipt.status}{receipt.detail && <p>{receipt.detail}</p>}</li>)}</ol><p>邮件发送与关键决定须由负责人另行确认，聊天不构成批准。</p></details>}
        {!!message.references.length && <div className={s.references} aria-label="原文依据">{message.references.map((reference, index) => <a key={`${reference.case_id}-${reference.anchor?.section || "case"}-${index}`} href={referenceHref(reference)} onClick={event => intercept(event, () => onReference(reference))}>{reference.label}{reference.anchor && <span>{reference.anchor.version.toUpperCase()}</span>}</a>)}</div>}
        {message.action && <a className={s.action} href={actionHref(message.action)} onClick={event => intercept(event, () => onAction(message.action!))}>{message.action.type === "navigate" ? viewLabels[message.action.view] : "应用到工作列表"}</a>}
      </article>)}
      {sending && <p className={s.status} role="status">正在整理回复…</p>}
    </div>
    {newMessages && <button type="button" className={s.latest} onClick={() => { const element = transcript.current; if (element) element.scrollTop = element.scrollHeight; nearBottom.current = true; setNewMessages(false); }}>查看最新消息</button>}
    {refreshError && <div className={s.error} role="alert"><p>回复已保存，工作材料尚未刷新。</p><button type="button" onClick={() => void refreshState()}>刷新工作材料</button></div>}
    {tools && <details className={s.tools}><summary>模拟检查工具</summary><div className={s.toolBody}>{tools}</div></details>}
    <form className={s.composer} onSubmit={submit}>
      {sendError && <div className={s.error} role="alert"><p>{sendError}</p>{pending && <button type="button" disabled={sending} onClick={() => void send(pending.message, pending)}>重试消息</button>}</div>}
      <label className={s.srOnly} htmlFor="editorial-conversation-message">对话消息</label>
      <textarea id="editorial-conversation-message" ref={composer} name="editorial-conversation-message" autoComplete="off" aria-label="对话消息" placeholder="询问稿件、查找依据，或准备下一步草稿…" value={draft} maxLength={2000} rows={2} disabled={!!pending} onChange={event => { setDraft(event.target.value); saveLocal(event.target.value, null); }} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current && event.keyCode !== 229) { event.preventDefault(); void send(draft); }
      }}/>
      <div className={s.composerFooter}><span>Enter 发送，Shift + Enter 换行</span><button type="submit" aria-label="发送消息" disabled={loading || !!historyError || !!pending || sending || !model?.available || modelError}>{sending ? "发送中…" : "发送消息"}</button></div>
    </form>
  </section>;
}
