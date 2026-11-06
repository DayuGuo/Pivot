"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { withRequestTimeout } from "../browser";
import Glyph from "../editorial/icons";
import styles from "./search.module.css";

type Kind = "conversation" | "manuscript" | "dossier";
export type SearchItem = { id: string; title: string; href: string; kind: Kind };
type Group = { kind: Kind; label: string; items: SearchItem[]; has_more: boolean };
type Props = {
  scope: string;
  onActivate?: (item: SearchItem, event: MouseEvent<HTMLAnchorElement>) => void;
  onQueryChange?: (query: string) => void;
};
type View = { phase: "idle" | "loading" | "ready" | "error" | "auth-error"; groups: Group[] };
type Position = { style: CSSProperties; theme: string; target: HTMLElement };
const empty = (phase: View["phase"]): View => ({ phase, groups: [] });
const normalize = (value: string) => value.trim().replace(/\s+/gu, " ");
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const ids = new RegExp(`^${uuid}$`);
const destinations: Record<Kind, RegExp> = {
  conversation: new RegExp(`^/\\?conversation=(${uuid})$`),
  manuscript: new RegExp(`^/(?:publishing)?\\?manuscript=(${uuid})$`),
  dossier: new RegExp(`^/library\\?dossier=(${uuid})$`),
};
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown, maximum: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= maximum;

function readGroups(value: unknown, query: string): Group[] {
  if (!object(value) || value.query !== query || !Array.isArray(value.groups) || value.groups.length > 3) throw new Error("invalid_search_response");
  const seen = new Set<string>();
  return value.groups.map(group => {
    if (!object(group) || typeof group.kind !== "string" || !Object.hasOwn(destinations, group.kind) || !text(group.label, 80) || !Array.isArray(group.items) || group.items.length > 8 || typeof group.has_more !== "boolean") throw new Error("invalid_search_group");
    const kind = group.kind as Kind;
    if (seen.has(kind)) throw new Error("duplicate_search_group");
    seen.add(kind);
    const itemIds = new Set<string>();
    const items = group.items.map(item => {
      if (!object(item) || typeof item.id !== "string" || !ids.test(item.id) || !text(item.title, 1000) || typeof item.href !== "string") throw new Error("invalid_search_item");
      const target = destinations[kind].exec(item.href);
      if (!target || target[1].toLowerCase() !== item.id.toLowerCase() || itemIds.has(item.id.toLowerCase())) throw new Error("invalid_search_destination");
      itemIds.add(item.id.toLowerCase());
      return { id: item.id, title: item.title, href: item.href, kind };
    });
    return { kind, label: group.label, items, has_more: group.has_more };
  });
}

export default function GlobalSearch({ scope, ...props }: Props) {
  return <ScopedSearch key={scope} {...props} />;
}

function ScopedSearch({ onActivate, onQueryChange }: Omit<Props, "scope">) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<View>(() => empty("idle"));
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<Position | null>(null);
  const [composing, setComposing] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const debounce = useRef<number | null>(null);
  const sequence = useRef(0);
  const mounted = useRef(false);
  const authLost = useRef(false);
  const suppressFocus = useRef(false);
  const pendingFocus = useRef<"first" | "last" | null>(null);
  const popupId = useId();

  const place = useCallback(() => {
    const field = input.current;
    if (!field) return;
    const rect = field.getBoundingClientRect();
    const viewport = window.visualViewport;
    const x = viewport?.offsetLeft ?? 0, y = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? window.innerWidth, height = viewport?.height ?? window.innerHeight;
    if (!field.getClientRects().length || !rect.width || !rect.height || rect.bottom < y || rect.top > y + height || rect.right < x || rect.left > x + width) {
      sequence.current += 1; controller.current?.abort(); pendingFocus.current = null;
      if (debounce.current !== null) { window.clearTimeout(debounce.current); debounce.current = null; }
      setPosition(null); setOpen(false); return;
    }
    const inset = 8, gap = 6;
    const availableBelow = Math.max(0, y + height - rect.bottom - inset - gap);
    const availableAbove = Math.max(0, rect.top - y - inset - gap);
    const below = availableBelow >= Math.min(240, availableAbove);
    const popupWidth = Math.max(0, Math.min(Math.max(rect.width, 320), width - inset * 2));
    const left = Math.max(x + inset, Math.min(rect.left, x + width - inset - popupWidth));
    const theme = field.closest("[data-theme]")?.getAttribute("data-theme") ?? "light";
    const target = field.closest<HTMLElement>('[aria-modal="true"]') ?? document.body;
    setPosition({
      style: { position: "fixed", left, width: popupWidth, maxHeight: Math.min(360, below ? availableBelow : availableAbove), ...(below ? { top: rect.bottom + gap } : { bottom: window.innerHeight - rect.top + gap }) },
      theme, target,
    });
  }, []);

  const cancel = useCallback(() => {
    sequence.current += 1; controller.current?.abort(); controller.current = null; pendingFocus.current = null;
    if (debounce.current !== null) { window.clearTimeout(debounce.current); debounce.current = null; }
  }, []);

  const lookup = useCallback(async (value: string, focus: "first" | "last" | null = null) => {
    if (authLost.current) return;
    cancel();
    pendingFocus.current = focus;
    const generation = sequence.current;
    const active = new AbortController(); controller.current = active;
    try {
      const groups = await withRequestTimeout(10_000, active.signal, async signal => {
        const response = await fetch(`/api/search?q=${encodeURIComponent(value)}&limit=8`, { credentials: "same-origin", cache: "no-store", signal });
        if ([401, 403].includes(response.status)) {
          if (mounted.current && generation === sequence.current && !active.signal.aborted) { authLost.current = true; setView(empty("auth-error")); }
          return null;
        }
        if (!response.ok) throw new Error("search_request_failed");
        return readGroups(await response.json(), value);
      });
      if (groups !== null && mounted.current && generation === sequence.current && !active.signal.aborted) {
        setView({ phase: "ready", groups });
        const destination = pendingFocus.current; pendingFocus.current = null;
        if (destination) window.requestAnimationFrame(() => {
          if (!mounted.current || generation !== sequence.current || document.activeElement !== input.current) return;
          const links = popup.current?.querySelectorAll<HTMLAnchorElement>("a[data-search-result]");
          (destination === "first" ? links?.[0] : links?.[links.length - 1])?.focus();
        });
      }
    } catch {
      if (mounted.current && generation === sequence.current && !active.signal.aborted) { pendingFocus.current = null; setView(empty("error")); }
    } finally { if (controller.current === active) controller.current = null; }
  }, [cancel]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; cancel(); };
  }, [cancel]);

  useEffect(() => {
    const value = normalize(query);
    if (!value || composing || authLost.current) return;
    const timer = window.setTimeout(() => { debounce.current = null; void lookup(value, pendingFocus.current); }, 250);
    debounce.current = timer;
    return () => { window.clearTimeout(timer); cancel(); };
  }, [query, composing, lookup, cancel]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent | FocusEvent) => {
      const node = event.target;
      if (node instanceof Node && !root.current?.contains(node) && !popup.current?.contains(node)) { pendingFocus.current = null; setOpen(false); }
    };
    const viewport = window.visualViewport;
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    viewport?.addEventListener("resize", place);
    viewport?.addEventListener("scroll", place);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(place) : null;
    if (input.current) observer?.observe(input.current);
    const themeOwner = input.current?.closest("[data-theme]");
    const themes = typeof MutationObserver === "function" ? new MutationObserver(place) : null;
    if (themeOwner) themes?.observe(themeOwner, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true);
      viewport?.removeEventListener("resize", place); viewport?.removeEventListener("scroll", place);
      document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", outside);
      observer?.disconnect(); themes?.disconnect();
    };
  }, [open, place]);

  function closeAndFocus() {
    pendingFocus.current = null; setOpen(false);
    if (document.activeElement !== input.current) { suppressFocus.current = true; input.current?.focus(); }
  }

  function reopen(focus: "first" | "last" | null = null) {
    cancel(); place(); setOpen(true);
    setView(empty(authLost.current ? "auth-error" : "loading"));
    if (!authLost.current) void lookup(normalize(query), focus);
  }

  function keys(event: KeyboardEvent<HTMLDivElement>) {
    if (composing || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) { if (event.key === "Enter") event.stopPropagation(); return; }
    if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); closeAndFocus(); return; }
    const links = Array.from(popup.current?.querySelectorAll<HTMLAnchorElement>("a[data-search-result]") ?? []);
    if (event.target === input.current) {
      if (["ArrowDown", "ArrowUp"].includes(event.key) && normalize(query)) {
        event.preventDefault();
        const first = event.key === "ArrowDown";
        if (!open) { reopen(first ? "first" : "last"); return; }
        place();
        if (links.length) (first ? links[0] : links.at(-1))?.focus();
        else if (view.phase === "loading") pendingFocus.current = first ? "first" : "last";
      } else if (event.key === "Enter") event.preventDefault();
      return;
    }
    const current = links.indexOf(event.target as HTMLAnchorElement);
    if (current < 0 || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const next = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
    links[next]?.focus();
  }

  const visible = open && !!normalize(query) && !!position;
  const hasItems = view.groups.some(group => group.items.length > 0);
  return <div ref={root} className={styles.root} role="search" onKeyDown={keys}>
    <span className={styles.icon}><Glyph name="search" size={16} /></span>
    <input ref={input} className={styles.input} type="search" aria-label="全局搜索" placeholder="搜索…" name="global-search" autoComplete="off" spellCheck={false} maxLength={160} value={query} aria-controls={visible ? popupId : undefined} aria-busy={view.phase === "loading"}
      onChange={event => {
        const value = event.target.value; cancel(); setQuery(value); onQueryChange?.(value);
        setView(empty(authLost.current ? "auth-error" : normalize(value) ? "loading" : "idle"));
        place(); setOpen(!!normalize(value));
      }}
      onFocus={() => { if (suppressFocus.current) { suppressFocus.current = false; return; } if (normalize(query) && !open) reopen(); }}
      onCompositionStart={() => { cancel(); setComposing(true); }} onCompositionEnd={() => setComposing(false)} />
    {visible && createPortal(<div ref={popup} id={popupId} className={styles.popover} data-theme={position.theme} style={position.style} role="region" aria-label="搜索结果">
      {view.phase === "loading" && <p className={styles.message} role="status">正在搜索…</p>}
      {view.phase === "error" && <div className={styles.feedback}><p className={styles.error} role="alert">搜索暂时不可用，请重试。</p><button type="button" className={styles.retry} onClick={() => { cancel(); setView(empty("loading")); void lookup(normalize(query)); }}>重新搜索</button></div>}
      {view.phase === "auth-error" && <p className={`${styles.message} ${styles.error}`} role="alert">登录或身份已变化，请重新打开工作区。</p>}
      {view.phase === "ready" && !hasItems && <p className={styles.message} role="status">没有找到相关结果。</p>}
      {view.phase === "ready" && view.groups.filter(group => group.items.length > 0 || group.has_more).map(group => <section className={styles.group} key={group.kind} aria-labelledby={`${popupId}-${group.kind}`}>
        <h2 id={`${popupId}-${group.kind}`} className={styles.heading}>{group.label}</h2>
        <ul className={styles.items}>{group.items.map(item => <li key={item.id}><a data-search-result className={styles.result} href={item.href} onClick={event => { if (event.defaultPrevented) return; onActivate?.(item, event); setOpen(false); }}>{item.title}</a></li>)}</ul>
        {group.has_more && <p className={styles.more}>还有更多结果，请细化关键词</p>}
      </section>)}
    </div>, position.target)}
  </div>;
}
