"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { LibraryError, readJSON } from "./api";
import type { ReviewClaim, Session } from "./types";
import styles from "./library.module.css";
export type FeedbackContext = { dossierId: string; session: Session; onDenied: () => void; onDirty: (key: string, dirty: boolean) => void };
type Review = { id: string; verdict: string; note: string; review_no: number; created_at: string; claim_digest: string; content_digest: string };
type History = { items: Review[]; next_cursor: number | null; latest_id: string | null; claim_digest: string; content_digest: string };
const labels: Record<string, string> = { supported: "有依据", unsupported: "无依据", uncertain: "待核对" };
function validReview(value: Review, claimDigest: string, contentDigest: string) {
  return typeof value?.id === "string" && /^[0-9a-f-]{36}$/i.test(value.id) && Object.hasOwn(labels, value.verdict) && typeof value.note === "string" && value.note.trim().length >= 5 && Number.isSafeInteger(value.review_no) && value.review_no >= 1 && Number.isFinite(Date.parse(value.created_at)) && value.claim_digest === claimDigest && value.content_digest === contentDigest;
}
export default function ClaimFeedback({ context, answerId, bucket, index, claim }: { context: FeedbackContext; answerId: string; bucket: "claims" | "withheld_claims"; index: number; claim: ReviewClaim }) {
  const key = `${context.dossierId}:${answerId}:${bucket}:${index}`;
  const url = `/api/dossiers/${context.dossierId}/answers/${answerId}/claims/${bucket}/${index}/reviews`;
  const [opened, setOpened] = useState(false), [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<History | null>(null), [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [verdict, setVerdict] = useState("uncertain"), [note, setNote] = useState(""), [ack, setAck] = useState(false), [dirty, setDirty] = useState(false);
  const alive = useRef(true), running = useRef(false), request = useRef<{ key: string; id: string } | null>(null);
  const onDirty = context.onDirty;
  useEffect(() => { alive.current = true; return () => { alive.current = false; onDirty(key, false); }; }, [key, onDirty]);
  function changed() { setAck(false); setDirty(true); setNotice(""); onDirty(key, true); request.current = null; }
  function failed(e: unknown) {
    if (!alive.current) return;
    setError((e as Error).message);
    if (e instanceof LibraryError && [401, 403, 404].includes(e.status)) { setHistory(null); setNote(""); context.onDenied(); }
  }
  async function load(before?: number) {
    if (running.current) return;
    running.current = true; setBusy(true); setError("");
    try {
      const next = await readJSON<History>(url + (before ? `?before=${before}` : ""));
      if (!alive.current) return;
      if (next.content_digest !== claim.citations[0]?.content_digest) throw new LibraryError(409, "复核目标与当前显示结论不符，请重新载入资料。");
      if (!(next.latest_id === null || (typeof next.latest_id === "string" && /^[0-9a-f-]{36}$/i.test(next.latest_id))) || !(next.next_cursor === null || (Number.isSafeInteger(next.next_cursor) && next.next_cursor > 0)) || !/^[0-9a-f]{64}$/.test(next.claim_digest) || !Array.isArray(next.items) || next.items.length > 50 || !next.items.every(item => validReview(item, next.claim_digest, next.content_digest))) throw new LibraryError(502, "复核记录未完整收到，请重新载入。");
      if (!before) setAck(false);
      setHistory(previous => before && previous ? { ...next, latest_id: previous.latest_id, items: [...previous.items, ...next.items] } : next);
    } catch (e) { failed(e); } finally { running.current = false; if (alive.current) setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!history || !ack || running.current) return;
    running.current = true; setBusy(true); setError("");
    const payload = { content_digest: history.content_digest, claim_digest: history.claim_digest, expected_review_id: history.latest_id, verdict, note: note.trim(), acknowledged: true };
    const encoded = JSON.stringify(payload);
    if (request.current?.key !== encoded) request.current = { key: encoded, id: crypto.randomUUID() };
    try {
      const current = await readJSON<Session>("/api/publishing/session");
      if (!alive.current) return;
      const old = context.session;
      if (current.user.id !== old.user.id || current.journal.id !== old.journal.id || current.user.role !== old.user.role || current.csrf_token !== old.csrf_token) throw new LibraryError(401, "身份已变化，请重新登录核对；未提交复核。");
      const result = await readJSON<Review>(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": old.csrf_token }, body: JSON.stringify({ request_id: request.current!.id, ...payload }) });
      if (!alive.current) return;
      if (!validReview(result, history.claim_digest, history.content_digest) || result.verdict !== verdict || result.note !== payload.note) throw new LibraryError(502, "未完整收到保存回执；请保持内容不变，再次保存以恢复同一请求。");
      setHistory({ ...history, latest_id: result.id, items: [result, ...history.items.filter(item => item.id !== result.id)] });
      setAck(false); setDirty(false); onDirty(key, false); request.current = null;
      setNotice("人工复核已保存。");
    } catch (e) { failed(e); } finally { running.current = false; if (alive.current) setBusy(false); }
  }
  return <section aria-label="结论人工复核">
    <button type="button" aria-expanded={opened} onClick={() => { setOpened(!opened); if (!opened && !history) void load(); }}>人工复核</button>
    {opened && <div className={styles.references}>
      <p className={styles.hint}>仅记录这条结论的证据复核，不作稿件决定。</p>
      {history && <>{history.items[0] && <p className={styles.hint}>最近人工复核：{labels[history.items[0].verdict]} · 第 {history.items[0].review_no} 次</p>}<form className={styles.form} onSubmit={event => void submit(event)}>
        <fieldset disabled={busy}><label>复核意见<select aria-label="复核意见" name="claim-verdict" value={verdict} onChange={e => { setVerdict(e.target.value); changed(); }}>{Object.entries(labels).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>核对理由<textarea name="claim-note" autoComplete="off" required minLength={5} maxLength={2000} rows={3} value={note} onChange={e => { setNote(e.target.value); changed(); }} /></label>
        <label className={styles.checkbox}><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} /><span>本人已对照本版本的原文与完整结论核对</span></label></fieldset>
        <button type="submit" className={styles.primary} disabled={busy || !ack}>{busy ? "保存中…" : "保存人工复核"}</button>{dirty && <small>复核尚未保存</small>}
      </form><details><summary>复核记录（{history.items.length}）</summary>{history.items.map(item => <div key={item.id}><p>第 {item.review_no} 次 · {labels[item.verdict]} · {new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short" }).format(new Date(item.created_at))}</p><p>{item.note}</p></div>)}{history.next_cursor && <button type="button" disabled={busy} onClick={() => void load(history.next_cursor!)}>更早复核</button>}</details></>}
      {busy && !history && <p role="status">正在载入复核…</p>}{error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {error && <button type="button" disabled={busy} onClick={() => void load()}>重新载入复核记录</button>}
    </div>}
  </section>;
}
