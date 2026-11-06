"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { withRequestTimeout } from "../browser";

type Provider = "smtp" | "gmail" | "outlook";
type MailAccount = {
  id: string; provider: Provider; address: string; display_name: string;
  smtp_host: string | null; smtp_port: number | null; tls_mode: string | null;
  auth_mode: string; username: string | null; credential_ref: string | null;
  status: "unverified" | "verified" | "credentials_required" | "blocked" | "error" | "disconnected";
  last_error: string | null; last_checked_at: string | null; enabled: boolean; credentials_configured: boolean;
};
const providerNames = { smtp: "自托管 SMTP", gmail: "Gmail", outlook: "Outlook" };
const statusNames = { unverified: "尚未验证", verified: "已验证", credentials_required: "需要凭据", blocked: "连接被阻止", error: "验证失败", disconnected: "已断开" };

type MailState = { dirty: boolean; busy: boolean };
type MailProps = { csrf: string; journalId: string; onStateChange?: (state: MailState) => void };
type MailIdentity = { user: { id: string; role: string }; journal: { id: string }; csrf_token: string };
class MailError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
function validAccount(value: MailAccount) {
  return value && typeof value.id === "string" && typeof value.address === "string" && typeof value.display_name === "string" && Object.hasOwn(providerNames, value.provider) && Object.hasOwn(statusNames, value.status) && typeof value.credentials_configured === "boolean";
}
export default function MailSettings(props: MailProps) {
  return <MailSettingsForm key={`${props.journalId}:${props.csrf}`} {...props} />;
}
function MailSettingsForm({ csrf, journalId, onStateChange }: MailProps) {
  const [accounts, setAccounts] = useState<MailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [provider, setProvider] = useState<Provider>("smtp");
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [tls, setTls] = useState("starttls");
  const [auth, setAuth] = useState("password");
  const [username, setUsername] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [unknownResult, setUnknownResult] = useState(false);
  const [denied, setDenied] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true), generation = useRef(0), busyRef = useRef<string | null>(null), dirtyRef = useRef(false);
  const identity = useRef<string | null>(null), reads = useRef(new Set<AbortController>());
  const callback = useRef(onStateChange);
  useEffect(() => { callback.current = onStateChange; }, [onStateChange]);
  const active = useCallback((scope: number) => alive.current && scope === generation.current, []);
  const reportBusy = useCallback((value: string | null) => { busyRef.current = value; setBusy(value); callback.current?.({ dirty: dirtyRef.current, busy: value !== null }); }, []);
  const markDirty = useCallback(() => { dirtyRef.current = true; callback.current?.({ dirty: true, busy: busyRef.current !== null }); }, []);
  const request = useCallback(async <T,>(endpoint: string, body?: unknown): Promise<T> => {
    const readControl = body === undefined ? new AbortController() : null;
    if (readControl) reads.current.add(readControl);
    try {
      return await withRequestTimeout(body === undefined ? 15_000 : 60_000, readControl?.signal, async signal => {
        const response = await fetch(endpoint, {
          method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", signal,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        const result = await response.json().catch(() => null);
        if (!response.ok) throw new MailError(response.status, response.status === 401 ? "登录已失效，请重新登录后读取邮箱。" : response.status === 403 ? "当前身份无权访问邮箱设置。" : response.status === 422 ? "填写内容未通过校验，请检查后重试。" : `邮箱操作未完成 (${response.status})，请重新读取状态。`);
        if (!result || typeof result !== "object" || Array.isArray(result)) throw new MailError(502, "邮箱回执未完整收到，请重新读取状态。");
        return result as T;
      });
    } catch (cause) {
      if (cause instanceof MailError) throw cause;
      throw new MailError(0, "无法确认邮箱服务响应，请检查网络并重新读取状态。");
    } finally { if (readControl) reads.current.delete(readControl); }
  }, [csrf]);
  const authorize = useCallback(async (scope: number) => {
    if (!active(scope)) throw new MailError(401, "页面或身份已变化。");
    const current = await request<MailIdentity>("/api/publishing/session");
    if (!active(scope)) throw new MailError(401, "页面或身份已变化。");
    if (current.journal?.id !== journalId || current.csrf_token !== csrf || typeof current.user?.id !== "string" || typeof current.user.role !== "string") throw new MailError(401, "登录身份已变化，请重新登录核对。");
    const key = JSON.stringify([current.user.id, current.user.role, current.journal.id, current.csrf_token]);
    if (identity.current !== null && identity.current !== key) throw new MailError(401, "登录身份已变化，请重新登录核对。");
    identity.current = key;
  }, [active, request, csrf, journalId]);
  const fail = useCallback((cause: unknown, scope: number, write = false) => {
    if (!active(scope)) return;
    if (cause instanceof MailError && [401, 403].includes(cause.status)) {
      setAccounts([]); setDenied(true); setAddress(""); setDisplayName(""); setHost(""); setUsername(""); setCredentialRef("");
      dirtyRef.current = false; callback.current?.({ dirty: false, busy: busyRef.current !== null });
    } else if (write && (!(cause instanceof MailError) || cause.status === 0 || cause.status >= 500)) setUnknownResult(true);
    setError(cause instanceof Error ? cause.message : "邮箱操作未完成，请重新读取状态。");
  }, [active]);
  const readAccounts = useCallback(async (scope: number) => {
    await authorize(scope);
    const result = await request<{ accounts: MailAccount[] }>("/api/mail/accounts");
    await authorize(scope);
    if (!Array.isArray(result.accounts) || !result.accounts.every(validAccount)) throw new MailError(502, "邮箱列表未完整收到，请重新读取状态。");
    return result.accounts;
  }, [authorize, request]);
  useEffect(() => {
    alive.current = true; const scope = ++generation.current;
    void (async () => {
      try { const accounts = await readAccounts(scope); if (active(scope)) { setAccounts(accounts); setDenied(false); } }
      catch (cause) { fail(cause, scope); }
      finally { if (active(scope)) setLoading(false); }
    })();
    const controls = reads.current;
    return () => { alive.current = false; generation.current = scope + 1; for (const control of controls) control.abort(); controls.clear(); callback.current?.({ dirty: false, busy: false }); };
  }, [active, fail, readAccounts]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  async function reload() {
    if (busyRef.current) return; const scope = generation.current; reportBusy("read"); setError(""); setNotice("");
    try {
      const accounts = await readAccounts(scope); if (!active(scope)) return;
      setAccounts(accounts); setDenied(false); setUnknownResult(false); setNotice("邮箱状态已重新读取，请核对服务端记录后决定是否继续。");
    } catch (cause) { fail(cause, scope); } finally { if (active(scope)) reportBusy(null); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busyRef.current || loading || unknownResult || denied) return;
    const scope = generation.current; setError(""); setNotice("");
    const errors: Record<string, string> = {};
    if (!/^[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+$/.test(address.trim())) errors.address = "请输入有效邮箱地址";
    if (!displayName.trim()) errors.display_name = "请输入显示名称";
    else if (displayName.trim().length > 120 || /[\x00-\x1f\x7f]/.test(displayName)) errors.display_name = "显示名称须在 120 字以内且不含控制字符";
    if (provider === "smtp" && !host.trim()) errors.smtp_host = "请输入 SMTP 主机";
    else if (provider === "smtp" && !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(host.trim())) errors.smtp_host = "请填写域名或 IPv4 地址，不含协议、路径或端口";
    if (provider === "smtp" && (!/^\d+$/.test(port) || +port < 1 || +port > 65535)) errors.smtp_port = "端口须为 1–65535";
    if (credentialRef && !/^[A-Z][A-Z0-9_]{0,31}$/.test(credentialRef)) errors.credential_ref = "使用 1–32 位大写字母、数字或下划线，以字母开头";
    setFields(errors);
    if (Object.keys(errors).length) { requestAnimationFrame(() => formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return; }
    reportBusy("save"); let submitted = false;
    try {
      await authorize(scope); if (!active(scope)) return;
      submitted = true;
      const account = await request<MailAccount>("/api/mail/accounts", {
        provider, address: address.trim(), display_name: displayName.trim(),
        ...(provider === "smtp" ? { smtp_host: host.trim(), smtp_port: +port, tls_mode: tls, auth_mode: auth, username: username.trim() || undefined } : {}),
        credential_ref: credentialRef || undefined,
      });
      await authorize(scope); if (!active(scope)) return;
      if (!validAccount(account) || account.provider !== provider || account.address.toLowerCase() !== address.trim().toLowerCase()) throw new MailError(502, "邮箱回执未完整收到，请重新读取状态。");
      setAccounts(current => [account, ...current.filter(item => item.id !== account.id)]); setNotice("邮箱配置已保存，请验证连接。");
      dirtyRef.current = false; callback.current?.({ dirty: false, busy: true });
    } catch (cause) { fail(cause, scope, submitted); }
    finally { if (active(scope)) reportBusy(null); }
  }
  async function update(account: MailAccount, action: "verify" | "disconnect") {
    if (busyRef.current || unknownResult || denied) return;
    const scope = generation.current; reportBusy(account.id); setError(""); setNotice(""); let submitted = false;
    try {
      await authorize(scope); if (!active(scope)) return;
      submitted = true;
      const next = await request<MailAccount>(`/api/mail/accounts/${account.id}/${action}`, {});
      await authorize(scope); if (!active(scope)) return;
      if (!validAccount(next) || next.id !== account.id) throw new MailError(502, "邮箱回执未完整收到，请重新读取状态。");
      setAccounts(current => current.map(item => item.id === next.id ? next : item));
      setNotice(`${next.address}：${statusNames[next.status]}`);
    } catch (cause) { fail(cause, scope, submitted); }
    finally { if (active(scope)) reportBusy(null); }
  }
  function fieldError(name: string) { return fields[name] ? <small className="field-error" id={`error-${name}`}>{fields[name]}</small> : null; }
  const needsCredential = provider !== "smtp" || auth !== "none";
  return <div className="mail-settings">
    <div className="mail-title"><h2>邮箱</h2><span className="mail-send-disabled">真实邮件发送已禁用</span></div>
    <p className="mail-intro">保存连接配置并验证身份；凭据由管理员在服务器环境中配置。</p>
    {error && <div className="error" role="alert" ref={errorRef} tabIndex={-1}>{error}</div>}
    <div className="mail-notice" role="status" aria-live="polite">{notice}</div>
    {unknownResult && <p role="status">上次操作结果尚未确认。请先重新读取邮箱并核对服务端记录；本页不会自动重发。</p>}
    <button type="button" className="secondary" disabled={!!busy || loading} onClick={() => void reload()}>{busy === "read" ? "正在读取…" : "重新读取邮箱"}</button>
    {loading ? <p role="status">正在读取邮箱…</p> : !denied && <div className="mail-accounts" aria-label="已保存邮箱">{accounts.map(account => <article className="mail-account" key={account.id} data-testid="mail-account"><div className="mail-account-heading"><div><h3>{account.display_name}</h3><p>{account.address}</p></div><span className={`mail-status status-${account.status}`}>{statusNames[account.status]}</span></div><div className="mail-account-meta"><span>{providerNames[account.provider]}</span>{account.smtp_host && <span>{account.smtp_host}:{account.smtp_port}</span>}{account.status !== "disconnected" && <span>{account.auth_mode === "none" ? "无需凭据" : account.credentials_configured ? "凭据已配置" : "凭据未配置"}</span>}{account.last_checked_at && <time>最近验证 {new Date(account.last_checked_at).toLocaleString("zh-CN")}</time>}</div>{account.last_error && <p className="mail-account-error" role="status">{account.last_error}</p>}<div className="mail-account-actions"><button className="secondary" disabled={!!busy || unknownResult || account.status === "disconnected"} onClick={() => void update(account, "verify")}>{busy === account.id ? "处理中…" : "验证连接"}</button><button className="quiet-button" disabled={!!busy || unknownResult || account.status === "disconnected"} onClick={() => void update(account, "disconnect")}>断开连接</button></div></article>)}{!accounts.length && <p className="mail-empty">尚未绑定邮箱</p>}</div>}
    {!denied && <><form className="mail-form" onSubmit={save} onChange={markDirty} ref={formRef} noValidate>
      <fieldset disabled={!!busy || loading || unknownResult} style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
      <h3>绑定邮箱</h3><div className="form-field"><label htmlFor="mail-provider">服务商</label><select id="mail-provider" name="provider" value={provider} onChange={event => { setProvider(event.target.value as Provider); setFields({}); }}><option value="smtp">自托管 SMTP</option><option value="gmail">Gmail</option><option value="outlook">Outlook</option></select></div>
      <div className="form-grid"><div className="form-field"><label htmlFor="mail-address">邮箱地址</label><input id="mail-address" name="address" maxLength={254} type="email" autoComplete="off" spellCheck={false} value={address} onChange={event => setAddress(event.target.value)} aria-invalid={!!fields.address} aria-describedby={fields.address ? "error-address" : undefined}/>{fieldError("address")}</div><div className="form-field"><label htmlFor="mail-display">显示名称</label><input id="mail-display" name="display_name" maxLength={120} autoComplete="off" value={displayName} onChange={event => setDisplayName(event.target.value)} aria-invalid={!!fields.display_name} aria-describedby={fields.display_name ? "error-display_name" : undefined}/>{fieldError("display_name")}</div></div>
      {provider === "smtp" ? <><div className="form-grid smtp-grid"><div className="form-field"><label htmlFor="mail-host">SMTP 主机</label><input id="mail-host" name="smtp_host" maxLength={253} autoComplete="off" spellCheck={false} value={host} onChange={event => setHost(event.target.value)} aria-invalid={!!fields.smtp_host} aria-describedby={fields.smtp_host ? "error-smtp_host" : undefined}/>{fieldError("smtp_host")}</div><div className="form-field"><label htmlFor="mail-port">端口</label><input id="mail-port" name="smtp_port" type="number" inputMode="numeric" min={1} max={65535} autoComplete="off" value={port} onChange={event => setPort(event.target.value)} aria-invalid={!!fields.smtp_port} aria-describedby={fields.smtp_port ? "error-smtp_port" : undefined}/>{fieldError("smtp_port")}</div></div><div className="form-grid"><div className="form-field"><label htmlFor="mail-tls">连接安全</label><select id="mail-tls" name="tls_mode" value={tls} onChange={event => setTls(event.target.value)}><option value="starttls">STARTTLS</option><option value="tls">TLS</option><option value="none">无 TLS（仅本地 Mailpit）</option></select></div><div className="form-field"><label htmlFor="mail-auth">认证方式</label><select id="mail-auth" name="auth_mode" value={auth} onChange={event => setAuth(event.target.value)}><option value="password">密码（服务器环境）</option><option value="none">无需认证</option></select></div></div>{auth !== "none" && <div className="form-field"><label htmlFor="mail-user">SMTP 用户名</label><input id="mail-user" name="username" maxLength={254} autoComplete="off" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)}/></div>}<button type="button" className="text-button" onClick={() => { setHost("mailpit"); setPort("1025"); setTls("none"); setAuth("none"); setCredentialRef(""); setUsername(""); markDirty(); }}>使用本地 Mailpit</button></> : <p className="form-help">使用服务器配置的 OAuth 访问令牌验证邮箱身份。当前尚未提供授权登录和令牌续期界面。</p>}
      {needsCredential && <div className="form-field"><label htmlFor="mail-ref">凭据引用</label><input id="mail-ref" name="credential_ref" maxLength={32} autoComplete="off" spellCheck={false} placeholder="例如 EDITORIAL…" value={credentialRef} onChange={event => setCredentialRef(event.target.value)} aria-invalid={!!fields.credential_ref} aria-describedby={fields.credential_ref ? "error-credential_ref" : "credential-help"}/>{fieldError("credential_ref")}<small className="form-help" id="credential-help">仅填写引用名称，不要输入密码或令牌。</small></div>}
      <button className="primary save-mail" disabled={!!busy || loading || unknownResult}>{busy === "save" ? "正在保存…" : "保存邮箱"}</button>
      </fieldset>
    </form>
    <details className="setup-guide"><summary>服务器配置指南</summary><div><p>在服务器环境配置凭据，重新创建 API 容器后再验证。凭据值不要写入仓库、浏览器表单或日志。</p><p>例如引用 <code>EDITORIAL</code>：密码认证读取 <code>MAIL_CREDENTIAL_EDITORIAL_PASSWORD</code>；OAuth 读取 <code>MAIL_CREDENTIAL_EDITORIAL_ACCESS_TOKEN</code>。引用只能使用大写字母、数字、下划线，并以字母开头。</p><p>还需将 <code>MAIL_CREDENTIAL_EDITORIAL_JOURNAL_ID</code> 设置为当前期刊 ID：<code>{journalId}</code>。只有绑定到本期刊的引用才能读取凭据。</p><p>自托管 SMTP 须将精确主机和端口加入 <code>MAIL_SMTP_ALLOWLIST</code>，例如 <code>smtp.example.org:587</code>。外部服务器必须启用 TLS。默认仅允许本地 <code>mailpit:1025</code>，可无需凭据验证，不会发送邮件。</p><p>Gmail 需有效的 Google OAuth 访问令牌；Outlook 需有效的 Microsoft Graph 访问令牌，且邮箱身份必须一致。请由管理员完成相应提供商的授权和同意流程；本应用尚无 OAuth 授权或刷新令牌界面。</p><p>验证只检查连接和身份。保持 <code>EMAIL_SEND_ENABLED=false</code>；绑定或验证成功不会启用发送。</p></div></details></>}
  </div>;
}
