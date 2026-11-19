"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";

export function useWorkspaceDrawer(open: boolean, close: () => void, mobileQuery: string) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const opener = triggerRef.current;
    const media = window.matchMedia(mobileQuery);
    const resized = () => { if (!media.matches) close(); };
    media.addEventListener("change", resized);
    const frame = requestAnimationFrame(() => closeRef.current?.focus());
    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener("change", resized);
      requestAnimationFrame(() => {
        // A settings dialog takes over focus when opened from the drawer.
        if (!document.querySelector("dialog[open]") && opener?.isConnected && opener.getClientRects().length) opener.focus({ preventScroll: true });
      });
    };
  }, [open, close, mobileQuery]);
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!open || event.defaultPrevented) return;
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const controls = Array.from(panelRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]') ?? []).filter(element => element.tabIndex >= 0 && element.getClientRects().length > 0);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  return { panelRef, triggerRef, closeRef, onKeyDown };
}
