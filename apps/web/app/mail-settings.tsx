"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

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

export default function MailSettings({ csrf, journalId }: { csrf: string; journalId: string }) {
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
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const request = useCallback(async <T,>(path = "", body?: unknown): Promise<T> => {
    const response = await fetch(`/api/mail/accounts${path}`, {
      method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok) {
      if (Array.isArray(result.detail)) {
        const errors = Object.fromEntries(result.detail.map((item: {loc: string[]; msg: string}) => [item.loc.at(-1), item.msg]));
        setFields(errors);
      }
      throw new Error(typeof result.detail === "string" ? result.detail : `保存失败 (${response.status})，请检查填写内容`);
    }
    return result;
  }, [csrf]);
  useEffect(() => {
    let active = true;
    async function load() {
      try { const result = await request<{accounts: MailAccount[]}>(""); if (active) setAccounts(result.accounts); }
      catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "无法读取邮箱"); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [request]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  async function save(event: FormEvent) {
    event.preventDefault(); setError(""); setNotice("");
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
    setBusy("save");
    try {
      const account = await request<MailAccount>("", {
        provider, address: address.trim(), display_name: displayName.trim(),
        ...(provider === "smtp" ? { smtp_host: host.trim(), smtp_port: +port, tls_mode: tls, auth_mode: auth, username: username.trim() || undefined } : {}),
        credential_ref: credentialRef || undefined,
      });
      setAccounts(current => [account, ...current.filter(item => item.id !== account.id)]); setNotice("邮箱配置已保存，请验证连接。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败，请重试"); }
    finally { setBusy(null); }
  }
  async function update(account: MailAccount, action: "verify" | "disconnect") {
    setBusy(account.id); setError(""); setNotice("");
    try {
      const next = await request<MailAccount>(`/${account.id}/${action}`, {});
      setAccounts(current => current.map(item => item.id === next.id ? next : item));
      setNotice(`${next.address}：${statusNames[next.status]}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败，请重试"); }
    finally { setBusy(null); }
  }
  function fieldError(name: string) { return fields[name] ? <small className="field-error" id={`error-${name}`}>{fields[name]}</small> : null; }
  const needsCredential = provider !== "smtp" || auth !== "none";
  return <div className="mail-settings">
    <div className="mail-title"><h2>邮箱</h2><span className="mail-send-disabled">真实邮件发送已禁用</span></div>
    <p className="mail-intro">保存连接配置并验证身份；凭据由管理员在服务器环境中配置。</p>
    {error && <div className="error" role="alert" ref={errorRef} tabIndex={-1}>{error}</div>}
    <div className="mail-notice" role="status" aria-live="polite">{notice}</div>
    {loading ? <p role="status">正在读取邮箱…</p> : <div className="mail-accounts" aria-label="已保存邮箱">{accounts.map(account => <article className="mail-account" key={account.id} data-testid="mail-account"><div className="mail-account-heading"><div><h3>{account.display_name}</h3><p>{account.address}</p></div><span className={`mail-status status-${account.status}`}>{statusNames[account.status]}</span></div><div className="mail-account-meta"><span>{providerNames[account.provider]}</span>{account.smtp_host && <span>{account.smtp_host}:{account.smtp_port}</span>}{account.status !== "disconnected" && <span>{account.auth_mode === "none" ? "无需凭据" : account.credentials_configured ? "凭据已配置" : "凭据未配置"}</span>}{account.last_checked_at && <time>最近验证 {new Date(account.last_checked_at).toLocaleString("zh-CN")}</time>}</div>{account.last_error && <p className="mail-account-error" role="status">{account.last_error}</p>}<div className="mail-account-actions"><button className="secondary" disabled={!!busy || account.status === "disconnected"} onClick={() => void update(account, "verify")}>{busy === account.id ? "处理中…" : "验证连接"}</button><button className="quiet-button" disabled={!!busy || account.status === "disconnected"} onClick={() => void update(account, "disconnect")}>断开连接</button></div></article>)}{!accounts.length && <p className="mail-empty">尚未绑定邮箱</p>}</div>}
    <form className="mail-form" onSubmit={save} ref={formRef} noValidate>
      <h3>绑定邮箱</h3><div className="form-field"><label htmlFor="mail-provider">服务商</label><select id="mail-provider" name="provider" value={provider} onChange={event => { setProvider(event.target.value as Provider); setFields({}); }}><option value="smtp">自托管 SMTP</option><option value="gmail">Gmail</option><option value="outlook">Outlook</option></select></div>
      <div className="form-grid"><div className="form-field"><label htmlFor="mail-address">邮箱地址</label><input id="mail-address" name="address" maxLength={254} type="email" autoComplete="off" spellCheck={false} value={address} onChange={event => setAddress(event.target.value)} aria-invalid={!!fields.address} aria-describedby={fields.address ? "error-address" : undefined}/>{fieldError("address")}</div><div className="form-field"><label htmlFor="mail-display">显示名称</label><input id="mail-display" name="display_name" maxLength={120} autoComplete="off" value={displayName} onChange={event => setDisplayName(event.target.value)} aria-invalid={!!fields.display_name} aria-describedby={fields.display_name ? "error-display_name" : undefined}/>{fieldError("display_name")}</div></div>
      {provider === "smtp" ? <><div className="form-grid smtp-grid"><div className="form-field"><label htmlFor="mail-host">SMTP 主机</label><input id="mail-host" name="smtp_host" maxLength={253} autoComplete="off" spellCheck={false} value={host} onChange={event => setHost(event.target.value)} aria-invalid={!!fields.smtp_host} aria-describedby={fields.smtp_host ? "error-smtp_host" : undefined}/>{fieldError("smtp_host")}</div><div className="form-field"><label htmlFor="mail-port">端口</label><input id="mail-port" name="smtp_port" type="number" inputMode="numeric" min={1} max={65535} autoComplete="off" value={port} onChange={event => setPort(event.target.value)} aria-invalid={!!fields.smtp_port} aria-describedby={fields.smtp_port ? "error-smtp_port" : undefined}/>{fieldError("smtp_port")}</div></div><div className="form-grid"><div className="form-field"><label htmlFor="mail-tls">连接安全</label><select id="mail-tls" name="tls_mode" value={tls} onChange={event => setTls(event.target.value)}><option value="starttls">STARTTLS</option><option value="tls">TLS</option><option value="none">无 TLS（仅本地 Mailpit）</option></select></div><div className="form-field"><label htmlFor="mail-auth">认证方式</label><select id="mail-auth" name="auth_mode" value={auth} onChange={event => setAuth(event.target.value)}><option value="password">密码（服务器环境）</option><option value="none">无需认证</option></select></div></div>{auth !== "none" && <div className="form-field"><label htmlFor="mail-user">SMTP 用户名</label><input id="mail-user" name="username" maxLength={254} autoComplete="off" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)}/></div>}<button type="button" className="text-button" onClick={() => { setHost("mailpit"); setPort("1025"); setTls("none"); setAuth("none"); setCredentialRef(""); setUsername(""); }}>使用本地 Mailpit</button></> : <p className="form-help">使用服务器配置的 OAuth 访问令牌验证邮箱身份。当前尚未提供授权登录和令牌续期界面。</p>}
      {needsCredential && <div className="form-field"><label htmlFor="mail-ref">凭据引用</label><input id="mail-ref" name="credential_ref" maxLength={32} autoComplete="off" spellCheck={false} placeholder="例如 EDITORIAL…" value={credentialRef} onChange={event => setCredentialRef(event.target.value)} aria-invalid={!!fields.credential_ref} aria-describedby={fields.credential_ref ? "error-credential_ref" : "credential-help"}/>{fieldError("credential_ref")}<small className="form-help" id="credential-help">仅填写引用名称，不要输入密码或令牌。</small></div>}
      <button className="primary save-mail" disabled={!!busy}>{busy === "save" ? "正在保存…" : "保存邮箱"}</button>
    </form>
    <details className="setup-guide"><summary>服务器配置指南</summary><div><p>在服务器环境配置凭据，重新创建 API 容器后再验证。凭据值不要写入仓库、浏览器表单或日志。</p><p>例如引用 <code>EDITORIAL</code>：密码认证读取 <code>MAIL_CREDENTIAL_EDITORIAL_PASSWORD</code>；OAuth 读取 <code>MAIL_CREDENTIAL_EDITORIAL_ACCESS_TOKEN</code>。引用只能使用大写字母、数字、下划线，并以字母开头。</p><p>还需将 <code>MAIL_CREDENTIAL_EDITORIAL_JOURNAL_ID</code> 设置为当前期刊 ID：<code>{journalId}</code>。只有绑定到本期刊的引用才能读取凭据。</p><p>自托管 SMTP 须将精确主机和端口加入 <code>MAIL_SMTP_ALLOWLIST</code>，例如 <code>smtp.example.org:587</code>。外部服务器必须启用 TLS。默认仅允许本地 <code>mailpit:1025</code>，可无需凭据验证，不会发送邮件。</p><p>Gmail 需有效的 Google OAuth 访问令牌；Outlook 需有效的 Microsoft Graph 访问令牌，且邮箱身份必须一致。请由管理员完成相应提供商的授权和同意流程；本应用尚无 OAuth 授权或刷新令牌界面。</p><p>验证只检查连接和身份。保持 <code>EMAIL_SEND_ENABLED=false</code>；绑定或验证成功不会启用发送。</p></div></details>
  </div>;
}
