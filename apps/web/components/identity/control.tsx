"use client";
/* eslint-disable @next/next/no-html-link-for-pages -- Identity navigation must leave the current workspace through a native document navigation. */

import { useEffect, useRef, useState } from "react";
import Glyph from "../editorial/icons";
import { roleLabels } from "../publishing/types";
import { isSessionFailure, readIdentities, type IdentitySnapshot } from "./api";
import styles from "./identity.module.css";
import { useObservedIdentity } from "./boundary";

type User = { id: string; name: string; role: string };

type Props = { user: User; onNavigate?: () => void };

export default function IdentityControl(props: Props) {
  return <IdentityControlForUser key={`${props.user.id}:${props.user.role}`} {...props} />;
}

function IdentityControlForUser({ user, onNavigate }: Props) {
  useObservedIdentity(user);
  const [snapshot, setSnapshot] = useState<IdentitySnapshot | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const disclosure = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; controller.current?.abort(); };
  }, []);

  async function refresh() {
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    const current = ++generation.current;
    setChecking(true); setSnapshot(null); setError(""); setSignedOut(false);
    try {
      const result = await readIdentities(active.signal);
      if (!mounted.current || current !== generation.current || active.signal.aborted) return;
      if (result.user.id !== user.id || result.active_role !== user.role) {
        setError("当前身份已变化，请重新打开工作区。");
        return;
      }
      setSnapshot(result);
    } catch (failure) {
      if (!mounted.current || current !== generation.current || active.signal.aborted) return;
      setSnapshot(null); setSignedOut(isSessionFailure(failure));
      setError(isSessionFailure(failure) ? "登录已失效，请重新登录。" : "无法读取可用身份，请检查连接后重试。");
    } finally {
      if (mounted.current && current === generation.current) setChecking(false);
    }
  }

  const currentSnapshot = snapshot?.user.id === user.id && snapshot.active_role === user.role ? snapshot : null;
  return <details className={styles.control} ref={disclosure} onToggle={event => {
    if (event.currentTarget.open) void refresh();
    else { generation.current += 1; controller.current?.abort(); }
  }} onKeyDown={event => {
    if (event.key === "Escape" && disclosure.current?.open) {
      event.preventDefault(); event.stopPropagation(); disclosure.current.open = false;
      disclosure.current.querySelector("summary")?.focus();
    }
  }}>
    <summary className={styles.summary} aria-label="切换身份">
      <span className={styles.avatar} aria-hidden="true">{Array.from(user.name.trim())[0] || <Glyph name="people" size={16} />}</span>
      <span className={styles.person}><strong>{user.name}</strong><span>{roleLabels[user.role] ?? user.role}</span></span>
      <span className={styles.chevron} aria-hidden="true" />
    </summary>
    <div className={styles.options}>
      {checking && <p role="status">正在读取身份…</p>}
      {!checking && error && <><p className={styles.error} role="alert">{error}</p>{signedOut ? <a href="/" onClick={onNavigate}>重新登录</a> : <><button type="button" onClick={() => void refresh()}>重新读取身份</button><a href="/publishing" onClick={onNavigate}>重新打开工作区</a></>}</>}
      {!checking && !error && currentSnapshot && <ul aria-label="当前账号的可用身份">{currentSnapshot.roles.map(role => <li key={role}>{role === currentSnapshot.active_role
        ? <span className={styles.current} aria-current="true"><span>{roleLabels[role]}</span><span className={styles.currentMark}><Glyph name="check" size={15} />当前</span></span>
        : <a href={`/identity?role=${encodeURIComponent(role)}`} onClick={onNavigate}>{roleLabels[role]}</a>}</li>)}</ul>}
    </div>
  </details>;
}
