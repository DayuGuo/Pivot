"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { withRequestTimeout } from "../browser";
import Glyph from "../editorial/icons";
import styles from "./calendar.module.css";

type Route = { month: string; tz: string; view: "month" | "overdue"; day: string | null };
type Item = { id: string; manuscript_id: string; title: string; number: string; label: string; due_at: string; status: string; overdue: boolean; href: string };
type Data = { month: string; timezone: string; view: string; day: string | null; server_now: string; days: { date: string; count: number }[]; counts: { month: number; overdue: number; undated: number }; items: Item[]; next_cursor: string | null };
class CalendarError extends Error {}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const integer = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
function validate(value: unknown, route: Route): Data {
  if (!value || typeof value !== "object") throw new CalendarError("日历响应不完整，请重新载入。");
  const d = value as Data;
  if (d.month !== route.month || d.timezone !== route.tz || d.view !== route.view || d.day !== route.day || typeof d.server_now !== "string" || !Number.isFinite(Date.parse(d.server_now)) || !d.counts || ![d.counts.month, d.counts.overdue, d.counts.undated].every(integer) || !Array.isArray(d.days) || d.days.length > 31 || !Array.isArray(d.items) || d.items.length > 12 || !(d.next_cursor === null || typeof d.next_cursor === "string" && d.next_cursor.length <= 1000)) throw new CalendarError("日历响应不完整，请重新载入。");
  if (d.days.some(x => !x || !new RegExp(`^${route.month}-[0-9]{2}$`).test(x.date) || !integer(x.count) || x.count < 1 || !Number.isFinite(Date.parse(x.date))) || new Set(d.days.map(x => x.date)).size !== d.days.length) throw new CalendarError("日历日期无效，请重新载入。");
  if (d.items.some(x => !x || !uuid.test(x.id) || !uuid.test(x.manuscript_id) || typeof x.title !== "string" || x.title.length > 1000 || typeof x.label !== "string" || x.label.length > 100 || typeof x.number !== "string" || typeof x.overdue !== "boolean" || typeof x.due_at !== "string" || !Number.isFinite(Date.parse(x.due_at)) || x.href !== `/publishing?manuscript=${x.manuscript_id}`) || new Set(d.items.map(x => x.id)).size !== d.items.length) throw new CalendarError("日历目标无效，请重新载入。");
  return d;
}
function today(tz?: string) {
  if (tz) {
    const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: tz }).formatToParts(new Date());
    const value = (kind: string) => parts.find(part => part.type === kind)!.value;
    return `${value("year")}-${value("month")}-${value("day")}`;
  }
  const d = new Date();
  return `${String(d.getFullYear()).padStart(4, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function shift(month: string, amount: number) {
  const [year, number] = month.split("-").map(Number);
  const n = year * 12 + number - 1 + amount;
  const y = Math.floor(n / 12);
  return y >= 1 && y <= 9998 ? `${String(y).padStart(4, "0")}-${String(n % 12 + 1).padStart(2, "0")}` : null;
}
const monthText = (m: string) => new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", timeZone: "UTC" }).format(new Date(`${m}-01T12:00:00Z`));

export default function PersonalCalendar({ scope, revision = null }: { scope: string; revision?: string | null }) {
  return <Calendar key={scope} revision={revision} />;
}

function Calendar({ revision }: { revision: string | null }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [route, setRoute] = useState<Route>({ month: "", tz: "UTC", view: "month", day: null });
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const [utcFallback, setUtcFallback] = useState(false);
  const [focusDay, setFocusDay] = useState("");
  const table = useRef<HTMLTableElement>(null);
  const control = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const retryCursor = useRef<string | null>(null);
  const pendingFocus = useRef<string | null>(null);
  const observedRevision = useRef<string | null>(revision);
  const target = new URLSearchParams({ month: route.month, tz: route.tz, view: route.view, ...(route.day ? { day: route.day } : {}) }).toString();
  const load = useCallback(async (cursor: string | null = null) => {
    const seq = ++sequence.current;
    control.current?.abort();
    const next = new AbortController(); control.current = next;
    retryCursor.current = cursor;
    try {
      const response = await withRequestTimeout(10_000, next.signal, async signal => {
        const raw = await fetch(`/api/calendar?${target}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`, { credentials: "same-origin", cache: "no-store", signal });
        return { status: raw.status, ok: raw.ok, body: raw.ok ? await raw.json() : null };
      });
      if (seq !== sequence.current || next.signal.aborted) return;
      if ([401, 403].includes(response.status)) { setData(null); setDenied(true); throw new CalendarError("身份已失效，请重新打开工作区。"); }
      if (response.status === 422) {
        retryCursor.current = null; setData(null);
        if (!cursor && route.tz !== "UTC") { setUtcFallback(true); throw new CalendarError("当前时区暂不受支持，可使用 UTC 查看。"); }
        throw new CalendarError("日历或分页位置已失效，请重新载入。");
      }
      if (!response.ok) throw new CalendarError(response.status === 429 ? "服务繁忙，请稍后重新载入日历。" : "无法载入日历，请重试。");
      const value = validate(response.body, route);
      if (seq !== sequence.current || next.signal.aborted) return;
      setData(previous => cursor && previous ? { ...value, items: [...new Map([...previous.items, ...value.items].map(item => [item.id, item])).values()] } : value);
      setError("");
    } catch (failure) {
      if (seq === sequence.current && !next.signal.aborted) setError(failure instanceof CalendarError ? failure.message : "无法载入日历，请检查连接后重试。");
    } finally { if (seq === sequence.current) setLoading(false); }
  }, [target, route]);
  const cancel = useCallback(() => { ++sequence.current; control.current?.abort(); }, []);
  useEffect(() => {
    // Commit the disclosure/filter before starting its cancellable external read.
    const timer = window.setTimeout(() => { if (open && !denied) void load(); }, 0);
    return () => { window.clearTimeout(timer); cancel(); };
  }, [open, denied, load, cancel]);
  useEffect(() => {
    const previous = observedRevision.current; observedRevision.current = revision;
    // The first workspace load establishes a baseline, not a new identity/query.
    if (previous === null || revision === null || previous === revision || !open || denied) return;
    const timer = window.setTimeout(() => {
      cancel(); setData(null); setError(""); setLoading(true); void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [revision, open, denied, load, cancel]);
  useLayoutEffect(() => {
    if (!pendingFocus.current) return;
    table.current?.querySelector<HTMLButtonElement>(`button[data-date="${pendingFocus.current}"]`)?.focus();
    pendingFocus.current = null;
  }, [route.month, focusDay]);
  function change(next: Route) {
    ++sequence.current; control.current?.abort(); setData(null); setError(""); setUtcFallback(false); setLoading(true); setRoute(next);
  }
  function toggle() {
    cancel(); setData(null); setError(denied ? "身份已失效，请重新打开工作区。" : "");
    if (!open) {
      if (!route.month) {
        const date = today(); let tz = "UTC";
        try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { /* UTC is explicit. */ }
        setRoute({ month: date.slice(0, 7), tz, view: "month", day: null }); setFocusDay(date);
      }
      setLoading(!denied);
    }
    setOpen(!open);
  }
  function moveMonth(amount: number) {
    const month = shift(route.month, amount);
    if (month) { setFocusDay(`${month}-01`); change({ ...route, month, day: null, view: "month" }); }
  }
  function dayKey(event: KeyboardEvent<HTMLButtonElement>, value: string) {
    const offsets: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (!(event.key in offsets)) return;
    event.preventDefault();
    const date = new Date(`${value}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + offsets[event.key]);
    const next = date.toISOString().slice(0, 10); if (Number(next.slice(0, 4)) < 1 || Number(next.slice(0, 4)) > 9998) return;
    pendingFocus.current = next; setFocusDay(next);
    if (next.slice(0, 7) !== route.month) change({ ...route, month: next.slice(0, 7), day: null, view: "month" });
  }
  const first = route.month ? new Date(`${route.month}-01T12:00:00Z`) : null;
  const offset = first ? (first.getUTCDay() + 6) % 7 : 0;
  const last = first ? new Date(first) : null; if (last) { last.setUTCMonth(last.getUTCMonth() + 1); last.setUTCDate(0); }
  const cells = Array.from({ length: Math.ceil((offset + (last?.getUTCDate() ?? 0)) / 7) * 7 }, (_, i) => i >= offset && i < offset + (last?.getUTCDate() ?? 0) ? `${route.month}-${String(i - offset + 1).padStart(2, "0")}` : null);
  const days = new Map(data?.days.map(x => [x.date, x.count]));
  const dateText = (date: string) => new Intl.DateTimeFormat("zh-CN", { year: route.view === "overdue" ? "numeric" : undefined, month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: route.tz }).format(new Date(date));
  const selectedFocus = focusDay.startsWith(route.month) ? focusDay : `${route.month}-01`;
  return <section className={styles.root} data-calendar-open={open ? "true" : undefined} aria-label="个人日历">
    <button className={styles.toggle} aria-expanded={open} aria-controls={id} onClick={toggle}><Glyph name="calendar" size={16} /><span>日历</span><Glyph name={open ? "close" : "arrow"} size={13} /></button>
    {open && route.month && <div className={styles.panel} id={id} aria-label="截止日期日历">
      <div className={styles.month}><button aria-label="上个月" disabled={!shift(route.month, -1) || denied} onClick={() => moveMonth(-1)}><Glyph name="back" size={14} /></button><strong>{monthText(route.month)}</strong><button aria-label="下个月" disabled={!shift(route.month, 1) || denied} onClick={() => moveMonth(1)}><Glyph name="arrow" size={14} /></button></div>
      <table ref={table} className={styles.grid} aria-label={monthText(route.month)}><thead><tr>{["一", "二", "三", "四", "五", "六", "日"].map(d => <th key={d} scope="col">{d}</th>)}</tr></thead><tbody>{Array.from({ length: cells.length / 7 }, (_, row) => <tr key={row}>{cells.slice(row * 7, row * 7 + 7).map((date, col) => <td key={date ?? col}>{date && <button data-date={date} disabled={denied} tabIndex={selectedFocus === date ? 0 : -1} aria-pressed={route.view === "month" && route.day === date} aria-label={`${date}，${days.get(date) ?? 0}项截止任务`} onFocus={() => setFocusDay(date)} onKeyDown={event => dayKey(event, date)} onClick={() => change({ ...route, view: "month", day: route.day === date ? null : date })}>{Number(date.slice(-2))}{days.has(date) && <i aria-hidden="true" />}</button>}</td>)}</tr>)}</tbody></table>
      <label className={styles.nativeDate}>截止日期<input type="date" name="calendar-date" autoComplete="off" min="0001-01-01" max="9998-12-31" value={route.day ?? ""} disabled={denied} onChange={event => { const date = event.target.value; if (!date || /^\d{4}-\d{2}-\d{2}$/.test(date)) change({ ...route, month: date ? date.slice(0, 7) : route.month, day: date || null, view: "month" }); }} /></label>
      <div className={styles.views}><button aria-pressed={route.view === "month" && !route.day} disabled={denied} onClick={() => change({ ...route, view: "month", day: null })}>本月{data ? ` ${data.counts.month}` : ""}</button><button aria-pressed={route.view === "overdue"} disabled={denied} onClick={() => change({ ...route, view: "overdue", day: null })}>逾期{data ? ` ${data.counts.overdue}` : ""}</button><button disabled={denied} onClick={() => { const date = today(route.tz); setFocusDay(date); change({ ...route, month: date.slice(0, 7), day: date, view: "month" }); }}>今天</button></div>
      {error && <div className={styles.error} role="alert"><p>{error}</p>{denied ? <Link href="/publishing">重新打开工作区</Link> : utcFallback ? <button onClick={() => change({ ...route, tz: "UTC", day: null })}>使用 UTC</button> : <button disabled={loading} onClick={() => { setLoading(true); setError(""); void load(retryCursor.current); }}>重新载入</button>}</div>}
      {loading && <p className={styles.message} role="status">正在载入…</p>}
      {data && <><ul className={styles.items} aria-label="截止任务">{data.items.map(item => <li key={item.id}><Link href={item.href}><strong>{item.label}</strong><span>{item.title || "未命名稿件"}</span><small><time dateTime={item.due_at}>{dateText(item.due_at)}</time>{item.overdue ? " · 逾期" : item.status === "waiting" ? " · 等待" : ""}</small></Link></li>)}</ul>{!loading && !data.items.length && <p className={styles.message} role="status">{route.view === "overdue" ? "没有逾期任务。" : route.day ? "这天没有截止任务。" : "本月没有截止任务。"}</p>}{data.next_cursor && <button className={styles.more} disabled={loading} onClick={() => { setLoading(true); setError(""); void load(data.next_cursor); }}>继续查看</button>}</>}
      <div className={styles.foot}><span aria-label={`显示时区 ${route.tz}`}>{route.tz}</span>{data && data.counts.undated > 0 && <Link href="/publishing">{data.counts.undated}项未设期限</Link>}</div>
    </div>}
  </section>;
}
