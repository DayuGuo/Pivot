"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { IdentityError, readIdentities } from "./api";
import styles from "./identity.module.css";

type Identity = { id: string; role: string };
const Observer = createContext<(identity: Identity) => void>(() => {});

export function useObservedIdentity(user: Identity) {
  const observe = useContext(Observer);
  useEffect(() => { observe({ id: user.id, role: user.role }); }, [observe, user.id, user.role]);
}

export function announceIdentityChange() {
  try { const channel = new BroadcastChannel("pivot-identity"); channel.postMessage("changed"); channel.close(); } catch { /* Focus revalidation is the browser fallback. */ }
}

export default function IdentityBoundary({ children }: { children: ReactNode }) {
  const expected = useRef<Identity | null>(null);
  const controller = useRef<AbortController | null>(null);
  const [changed, setChanged] = useState(false);
  const observe = useCallback((identity: Identity) => { expected.current = identity; }, []);
  useEffect(() => {
    let mounted = true;
    async function check() {
      if (!expected.current || window.location.pathname === "/identity") return;
      controller.current?.abort();
      const active = new AbortController(); controller.current = active;
      const original = expected.current;
      try {
        const current = await readIdentities(active.signal);
        if (mounted && !active.signal.aborted && expected.current === original && (current.user.id !== original.id || current.active_role !== original.role)) setChanged(true);
      } catch (failure) {
        if (mounted && !active.signal.aborted && expected.current === original && failure instanceof IdentityError && [401, 403].includes(failure.status)) setChanged(true);
      }
    }
    const visible = () => { if (document.visibilityState === "visible") void check(); };
    const pageshow = (event: PageTransitionEvent) => { if (event.persisted) void check(); };
    let channel: BroadcastChannel | null = null;
    try { channel = new BroadcastChannel("pivot-identity"); channel.onmessage = () => { void check(); }; } catch { /* Older browsers recheck on focus/visibility/pageshow. */ }
    window.addEventListener("focus", visible);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("pageshow", pageshow);
    return () => { mounted = false; controller.current?.abort(); channel?.close(); window.removeEventListener("focus", visible); document.removeEventListener("visibilitychange", visible); window.removeEventListener("pageshow", pageshow); };
  }, []);
  if (changed) return <main className={styles.page}><div className={styles.confirmation}><h1>当前身份已变化</h1><p role="alert">请重新进入工作区。旧页面的资料和操作已关闭。</p><a className={styles.primary} href="/publishing">进入当前身份工作区</a></div></main>;
  return <Observer.Provider value={observe}>{children}</Observer.Provider>;
}
