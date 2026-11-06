"use client";
/* eslint-disable @next/next/no-html-link-for-pages -- Authentication and identity recovery must open a fresh document with the current session. */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { readStorage, requestId, warnBeforeUnload, withRequestTimeout } from "../browser";
import Glyph from "../editorial/icons";
import { roleLabels } from "../publishing/types";
import { IdentityError, isSessionFailure, knownRole, readIdentities, validIdentity, type IdentitySnapshot } from "./api";
import { announceIdentityChange } from "./boundary";
import styles from "./identity.module.css";

type Stage = "reading" | "ready" | "writing" | "uncertain" | "signed-out" | "read-error";
function subscribeTheme(change: () => void) {
  window.addEventListener("storage", change);
  return () => window.removeEventListener("storage", change);
}
function themeSnapshot() {
  const value = readStorage("localStorage", "publishing-theme");
  return value === "light" || value === "dark" ? value : "system";
}

export default function IdentityConfirmation({ requestedRole }: { requestedRole: string | null }) {
  const [snapshot, setSnapshot] = useState<IdentitySnapshot | null>(null);
  const [stage, setStage] = useState<Stage>("reading");
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const generation = useRef(0);
  const reading = useRef<AbortController | null>(null);
  const writing = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const errorTarget = useRef<HTMLParagraphElement>(null);
  const theme = useSyncExternalStore(subscribeTheme, themeSnapshot, () => "system");

  const refresh = useCallback(async () => {
    if (busy.current) return;
    reading.current?.abort();
    const active = new AbortController(); reading.current = active;
    const current = ++generation.current;
    setStage("reading"); setSnapshot(null); setError("");
    try {
      const result = await readIdentities(active.signal);
      if (!mounted.current || current !== generation.current || active.signal.aborted) return;
      setSnapshot(result); setStage("ready");
    } catch (failure) {
      if (!mounted.current || current !== generation.current || active.signal.aborted) return;
      setSnapshot(null); setStage(isSessionFailure(failure) ? "signed-out" : "read-error");
      setError(isSessionFailure(failure) ? "登录已失效，请重新登录。" : "无法读取当前身份，请检查连接后重新核对。");
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    // Read the authenticated snapshot once; subsequent recovery always needs an explicit click.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    const unload = (event: BeforeUnloadEvent) => { if (busy.current) warnBeforeUnload(event); };
    window.addEventListener("beforeunload", unload);
    return () => {
      mounted.current = false; generation.current += 1;
      reading.current?.abort(); writing.current?.abort();
      window.removeEventListener("beforeunload", unload);
    };
  }, [refresh]);

  useEffect(() => { if (error) errorTarget.current?.focus(); }, [error]);

  const permitted = !!snapshot && knownRole(requestedRole) && snapshot.roles.includes(requestedRole);
  const alreadyCurrent = permitted && snapshot.active_role === requestedRole;
  const invalidRole = !knownRole(requestedRole) || (stage === "ready" && !permitted);

  async function changeIdentity() {
    if (busy.current || stage !== "ready" || !snapshot || !knownRole(requestedRole) || !snapshot.roles.includes(requestedRole) || snapshot.active_role === requestedRole) return;
    let id: string;
    try { id = requestId(); } catch { setError("浏览器无法安全准备切换请求，请升级浏览器后重试。"); return; }
    busy.current = true;
    reading.current?.abort();
    const active = new AbortController(); writing.current = active;
    const current = ++generation.current;
    setStage("writing"); setError("");
    try {
      await withRequestTimeout(30000, active.signal, async signal => {
        const response = await fetch("/api/auth/identity", {
          method: "POST", credentials: "same-origin", cache: "no-store", signal,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": snapshot.csrf_token },
          body: JSON.stringify({ role: requestedRole, request_id: id }),
        });
        if (!response.ok) throw new IdentityError(response.status);
        const value: unknown = await response.json();
        if (!validIdentity(value) || value.user.id !== snapshot.user.id || value.journal.id !== snapshot.journal.id || value.active_role !== requestedRole) throw new IdentityError(502);
      });
      if (!mounted.current || current !== generation.current) return;
      // The response has installed the rotated session cookie. A fresh document owns the new role.
      busy.current = false;
      announceIdentityChange();
      window.location.replace("/publishing");
    } catch (failure) {
      if (!mounted.current || current !== generation.current) return;
      setSnapshot(null);
      setStage(isSessionFailure(failure) ? "signed-out" : "uncertain");
      setError(isSessionFailure(failure) ? "登录或身份已变化，请重新登录核对。" : "切换结果尚未确认。请先核对当前身份，再决定是否重试。");
    } finally {
      if (mounted.current && current === generation.current) busy.current = false;
    }
  }

  return <main className={styles.page} data-theme={theme}>
    <div className={styles.confirmation}>
      <a className={styles.back} href="/publishing"><Glyph name="back" size={16} />返回工作区</a>
      <h1>切换身份</h1>
      {stage === "reading" && <p role="status">正在核对当前身份…</p>}
      {error && <p className={styles.error} role="alert" ref={errorTarget} tabIndex={-1}>{error}</p>}
      {snapshot && <dl className={styles.facts}>
        <dt>账号</dt><dd>{snapshot.user.name}<span>{snapshot.user.email}</span></dd>
        <dt>期刊</dt><dd>{snapshot.journal.name}</dd>
        <dt>当前身份</dt><dd>{roleLabels[snapshot.active_role]}</dd>
        {permitted && !alreadyCurrent && <><dt>切换为</dt><dd>{roleLabels[requestedRole!]}</dd></>}
      </dl>}
      {invalidRole && stage === "ready" && <p className={styles.error} role="alert">当前账号没有这个可用身份，请返回工作区重新选择。</p>}
      {stage === "ready" && permitted && <>
        <p>{alreadyCurrent ? `当前已是${roleLabels[requestedRole!]}。` : "确认后将重新打开该身份的工作区。"}</p>
        <div className={styles.actions}>{alreadyCurrent
          ? <a className={styles.primary} href="/publishing">进入工作区</a>
          : <button className={styles.primary} type="button" onClick={() => void changeIdentity()}>切换为{roleLabels[requestedRole!]}</button>}
        </div>
      </>}
      {stage === "writing" && <button className={styles.primary} type="button" disabled aria-busy="true">正在切换身份…</button>}
      {(stage === "uncertain" || stage === "read-error") && <button className={styles.secondary} type="button" onClick={() => void refresh()}>核对当前身份</button>}
      {stage === "signed-out" && <a className={styles.primary} href="/">重新登录</a>}
    </div>
  </main>;
}
