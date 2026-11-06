"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode, type KeyboardEvent } from "react";
import Glyph from "../editorial/icons";
import { roleLabels as roles } from "../publishing/types";
import { withRequestTimeout, warnBeforeUnload } from "../browser";
import MailSettings from "./mail-settings";
import styles from "./settings.module.css";

type Tab = "model" | "mail" | "account";
type Session = {
  user: { id: string; name: string; email: string; role: string };
  journal: { id: string; name: string };
  csrf_token: string;
  model: { provider: string; model?: string | null; available: boolean; error_code?: string };
};
type Open = (tab: Tab) => void;
const SettingsContext = createContext<Open | null>(null);
const labels = { model: "模型 API", mail: "邮箱", account: "账号" };
function validSession(value: unknown): value is Session {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Session>;
  return !!item.user && !!item.journal && !!item.model &&
    [item.user.id, item.user.name, item.user.email, item.user.role, item.journal.id, item.journal.name, item.csrf_token].every(field => typeof field === "string" && !!field) &&
    typeof item.model.provider === "string" && typeof item.model.available === "boolean" &&
    (item.model.model == null || typeof item.model.model === "string");
}
class SettingsReadError extends Error { constructor(public status: number) { super("settings_read_failed"); } }
const scope = (session: Session) => [session.journal.id, session.user.id, session.user.role, session.csrf_token].join(":");

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [opened, setOpened] = useState<{ tab: Tab; theme: string } | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const open = useCallback((tab: Tab) => {
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpened({ tab, theme: trigger.current?.closest("[data-theme]")?.getAttribute("data-theme") ?? "light" });
  }, []);
  function close() {
    setOpened(null);
    requestAnimationFrame(() => { if (trigger.current?.isConnected && trigger.current.getClientRects().length) trigger.current.focus(); else Array.from(document.querySelectorAll<HTMLButtonElement>('button[aria-label="打开资料列表"], button[aria-label="打开工作列表"], button[aria-label="展开工作导航"], button[aria-label="打开导航"]')).find(button => button.getClientRects().length)?.focus(); });
  }
  return <SettingsContext.Provider value={open}>{children}{opened && <SettingsPanel initialTab={opened.tab} theme={opened.theme} close={close} />}</SettingsContext.Provider>;
}

export function SettingsButton({ className, tab = "model", onOpen }: { className?: string; tab?: Tab; onOpen?: () => void }) {
  const open = useContext(SettingsContext);
  return <button type="button" className={`${styles.launcher} ${className ?? ""}`} aria-haspopup="dialog" onClick={() => { onOpen?.(); open?.(tab); }}><Glyph name="settings" size={17} />设置</button>;
}

function SettingsPanel({ initialTab, theme, close }: { initialTab: Tab; theme: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState(initialTab);
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [visitedMail, setVisitedMail] = useState(initialTab === "mail");
  const dirty = useRef({ dirty: false, busy: false });
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const loadedSession = useRef<Session | null>(null);
  const updateMailState = useCallback((state: { dirty: boolean; busy: boolean }) => { dirty.current = state; }, []);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    setChecking(true); setError("");
    try {
      const value = await withRequestTimeout(15000, active.signal, async signal => {
        const response = await fetch("/api/publishing/session", { credentials: "same-origin", cache: "no-store", signal });
        if (!response.ok) throw new SettingsReadError(response.status);
        const result: unknown = await response.json();
        if (!validSession(result)) throw new SettingsReadError(502);
        return result;
      });
      if (!mounted.current || active.signal.aborted) return;
      if (!loadedSession.current || scope(loadedSession.current) !== scope(value)) dirty.current = { dirty: false, busy: false };
      loadedSession.current = value;
      setSession(value);
    } catch (failure) {
      if (!mounted.current || active.signal.aborted) return;
      if (failure instanceof SettingsReadError && [401, 403].includes(failure.status)) { loadedSession.current = null; setSession(null); dirty.current = { dirty: false, busy: false }; }
      setError("无法读取当前账号的设置。请检查连接，或关闭设置后重新登录。");
    } finally { if (mounted.current && controller.current === active) setChecking(false); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    const element = dialog.current;
    element?.showModal();
    // This effect loads an external authenticated snapshot and cancels obsolete reads.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    const unload = (event: BeforeUnloadEvent) => { if (dirty.current.dirty || dirty.current.busy) warnBeforeUnload(event); };
    window.addEventListener("focus", visible);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("beforeunload", unload);
    return () => { mounted.current = false; controller.current?.abort(); element?.close(); window.removeEventListener("focus", visible); document.removeEventListener("visibilitychange", visible); window.removeEventListener("beforeunload", unload); };
  }, [refresh]);
  function canClose() { return (!dirty.current.dirty && !dirty.current.busy) || window.confirm(dirty.current.busy ? "邮箱操作尚未结束。关闭后请重新打开设置核对结果。仍要关闭？" : "邮箱配置尚未保存，关闭并放弃这些修改？"); }
  function requestClose() { if (canClose()) close(); }
  const canMail = session && ["editor", "chief_editor"].includes(session.user.role);
  const selected = tab === "mail" && !canMail ? "model" : tab;
  const tabs: Tab[] = canMail ? ["model", "mail", "account"] : ["model", "account"];
  function select(next: Tab) { setTab(next); if (next === "mail") setVisitedMail(true); }
  function navigateTabs(event: KeyboardEvent<HTMLButtonElement>) {
    const index = tabs.indexOf(selected);
    const next = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs.at(-1) : ["ArrowDown", "ArrowRight"].includes(event.key) ? tabs[(index + 1) % tabs.length] : ["ArrowUp", "ArrowLeft"].includes(event.key) ? tabs[(index + tabs.length - 1) % tabs.length] : null;
    if (next) { event.preventDefault(); select(next); document.getElementById(`settings-tab-${next}`)?.focus(); }
  }
  return <dialog ref={dialog} className={styles.dialog} data-theme={theme} aria-labelledby="settings-title" onKeyDown={event => { event.stopPropagation(); if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") event.preventDefault(); }} onCancel={event => { event.preventDefault(); event.stopPropagation(); requestClose(); }}>
    <header className={styles.header}><h1 id="settings-title">设置</h1><button type="button" className={styles.close} aria-label="关闭设置" onClick={requestClose}><Glyph name="close" /></button></header>
    <div className={styles.layout}>
      <div className={styles.navigation} role="tablist" aria-label="设置分类">{tabs.map(value => <button type="button" key={value} role="tab" id={`settings-tab-${value}`} aria-selected={selected === value} aria-controls={`settings-panel-${value}`} tabIndex={selected === value ? 0 : -1} onKeyDown={navigateTabs} onClick={() => select(value)}><Glyph name={value === "model" ? "spark" : value === "mail" ? "inbox" : "people"} size={16} />{labels[value]}</button>)}</div>
      <div className={styles.content}>
        {checking && <p role="status">正在读取设置…</p>}
        {error && <div role="alert" className={styles.error}>{error}<button type="button" onClick={() => void refresh()}>重新读取设置</button></div>}
        {session && <div hidden={checking || !!error}>
          <section role="tabpanel" id="settings-panel-model" aria-labelledby="settings-tab-model" hidden={selected !== "model"}><ModelSettings session={session} refresh={refresh} checking={checking} /></section>
          {canMail && visitedMail && <section role="tabpanel" id="settings-panel-mail" aria-labelledby="settings-tab-mail" hidden={selected !== "mail"}><MailSettings key={scope(session)} csrf={session.csrf_token} journalId={session.journal.id} onStateChange={updateMailState} /></section>}
          <section role="tabpanel" id="settings-panel-account" aria-labelledby="settings-tab-account" hidden={selected !== "account"}><h2>账号</h2><dl className={styles.facts}><dt>姓名</dt><dd>{session.user.name}</dd><dt>邮箱</dt><dd>{session.user.email}</dd><dt>当前身份</dt><dd>{roles[session.user.role] ?? session.user.role}</dd><dt>期刊</dt><dd>{session.journal.name}</dd></dl></section>
        </div>}
      </div>
    </div>
  </dialog>;
}

function ModelSettings({ session, refresh, checking }: { session: Session; refresh: () => Promise<void>; checking: boolean }) {
  const model = session.model;
  const mock = model.provider === "mock";
  const problem = model.error_code === "fresh_deepseek_key_required" ? "请在服务器安全环境中配置新的 DEEPSEEK_API_KEY。" : model.error_code === "editorial_live_access_requires_opt_in" ? "服务器尚未开启真实模型访问。" : "请检查服务器的模型配置。";
  return <><h2>模型 API</h2><dl className={styles.facts}><dt>服务商</dt><dd>{mock ? "Mock（模拟）" : model.provider === "deepseek" ? "DeepSeek" : "不可用"}</dd><dt>模型</dt><dd>{model.model || "未配置"}</dd>{model.provider === "deepseek" && <><dt>API 地址</dt><dd translate="no">https://api.deepseek.com/chat/completions</dd></>}<dt>配置状态</dt><dd>{mock ? "模拟模式，不调用真实模型" : model.available ? "已就绪，密钥由服务器安全环境提供" : "未就绪"}</dd></dl>{!model.available && <p className={styles.error} role="status">{problem}</p>}<button type="button" className="secondary" disabled={checking} onClick={() => void refresh()}>刷新模型配置</button><p className={styles.note}>这里只检查配置是否就绪，不向模型服务商发送测试请求。</p>
    <details className={styles.guide}><summary>配置 DeepSeek API</summary><p>由部署负责人将新密钥放入服务器安全环境。密钥不会显示在设置里，也不会写入浏览器存储或稿件资料。</p><dl className={styles.facts}><dt>服务商</dt><dd><code>EDITORIAL_MODEL_PROVIDER=deepseek</code></dd><dt>真实调用</dt><dd><code>EDITORIAL_MODEL_LIVE_ENABLED=true</code></dd><dt>密钥变量</dt><dd><code>DEEPSEEK_API_KEY</code></dd><dt>模型 ID</dt><dd><code>deepseek-flash</code></dd></dl><p>本机可运行 <code>python scripts/start-live-model.py</code>，在终端无回显输入新密钥。VPS 按私人部署包说明更新安全环境并重新创建 API 容器，再刷新这里的配置。</p><a href="https://github.com/DayuGuo/Pivot/blob/codex/single-journal-candidate/infrastructure/vps/README.md" target="_blank" rel="noreferrer">私人部署包配置说明</a></details><p className={styles.note}>模型只能提出建议。真实邮件发送继续禁用，关键决定仍由负责人确认。</p></>;
}
