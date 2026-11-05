"use client";
import { sha256Bytes, warnBeforeUnload } from "../browser";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Anchor, Candidate, Case, CaseState, PatchState } from "./types";
import { issueLabels } from "./types";
import s from "./review.module.css";

type Props = { manuscript: Case; state: CaseState; onSave: PatchState; onEvidence?: (anchor: Anchor) => void; storageScope?: string; prepare?: boolean; onDraftChange?: (patch: Partial<Omit<CaseState, "revision">> | null) => void };
type Patch = Partial<Omit<CaseState, "revision">>;
type SaveStatus = "idle" | "saving" | "saved" | "error";
type Snapshot = { kind: "invitation" | "decision"; to: string; subject: string; body: string; due?: string; outcome?: string; revision: number; digest: string };
const outcomes: Record<string, string> = { accept: "接收", minor_revision: "小修", major_revision: "大修", reject: "拒稿" };

function useSave(onSave: PatchState) {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState("");
  const last = useRef<Patch | null>(null);
  const busy = useRef(false);
  async function save(patch: Patch) {
    if (busy.current) return false;
    busy.current = true;
    last.current = patch;
    setStatus("saving");
    setError("");
    try { await onSave(patch); setStatus("saved"); return true; }
    catch (e) { setStatus("error"); setError(e instanceof Error ? e.message : "保存失败，请重试。"); return false; }
    finally { busy.current = false; }
  }
  return { status, error, save, retry: () => last.current && void save(last.current) };
}
function Feedback({ saver }: { saver: ReturnType<typeof useSave> }) {
  return <div className={s.feedback} aria-live="polite">{saver.status === "saving" ? "正在保存…" : saver.status === "saved" ? "已保存到工作区" : saver.status === "error" ? <span role="alert">{saver.error} <button type="button" onClick={saver.retry}>重试保存</button></span> : ""}</div>;
}
function useUnsaved(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const warn = warnBeforeUnload;
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}
function sameDraftShape(value: unknown, model: unknown): boolean {
  if (typeof model === "string") return typeof value === "string";
  if (!value || !model || typeof value !== "object" || typeof model !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(model);
  return Object.keys(value).length === keys.length && keys.every(key => sameDraftShape((value as Record<string, unknown>)[key], (model as Record<string, unknown>)[key]));
}
type CachedDraft<T> = { base: string; draft: T };
function useDraftPersistence<T extends object>({ draft, saved, cacheKey, restore, save, status, retainConflict }: { draft: T; saved: T; cacheKey?: string; status: SaveStatus; restore: (value: T) => void; save: (value: T) => Promise<boolean>; retainConflict?: (value: T) => boolean }) {
  const serialized = JSON.stringify(draft);
  const baseline = JSON.stringify(saved);
  const dirty = serialized !== baseline;
  const [ready, setReady] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [conflicts, setConflicts] = useState<CachedDraft<T>[]>([]);
  const latest = useRef({ serialized, baseline, draft, restore, save, retainConflict });
  useEffect(() => { latest.current = { serialized, baseline, draft, restore, save, retainConflict }; });
  useEffect(() => {
    let active = true;
    let pending: T | undefined;
    const retained: CachedDraft<T>[] = [];
    const retain = (value: unknown) => {
      if (!value || typeof value !== "object") return;
      const cached = value as CachedDraft<T>;
      if (typeof cached.base === "string" && sameDraftShape(cached.draft, latest.current.draft) && (latest.current.retainConflict?.(cached.draft) ?? true) && !retained.some(item => JSON.stringify(item.draft) === JSON.stringify(cached.draft))) retained.push(cached);
    };
    try {
      const raw = cacheKey && sessionStorage.getItem(cacheKey);
      if (raw) {
        const cached = JSON.parse(raw);
        if (Array.isArray(cached.conflicts)) cached.conflicts.forEach(retain);
        if (sameDraftShape(cached.draft, latest.current.draft)) {
          if (cached.base === latest.current.baseline) pending = cached.draft;
          else if (JSON.stringify(cached.draft) !== latest.current.baseline) retain(cached);
        }
      }
    } catch { /* A blocked or invalid browser cache never replaces database data. */ }
    queueMicrotask(() => {
      if (!active) return;
      if (pending) { latest.current.restore(pending); setRecovered(true); }
      setConflicts(retained);
      setReady(true);
    });
    return () => { active = false; };
  }, [cacheKey]);
  useEffect(() => {
    if (!ready) return;
    try {
      if (cacheKey) {
        if (dirty || conflicts.length) sessionStorage.setItem(cacheKey, JSON.stringify({ base: baseline, draft: JSON.parse(serialized), conflicts }));
        else sessionStorage.removeItem(cacheKey);
      }
    } catch { /* Database saves remain available without browser storage. */ }
    if (!dirty || status === "saving" || status === "error") return;
    const timer = setTimeout(() => {
      // The next render clears only the acknowledged draft. An older request must
      // never remove a newer edit or another mounted editor's retained conflict.
      void latest.current.save(JSON.parse(serialized) as T);
    }, 900);
    return () => clearTimeout(timer);
  }, [serialized, baseline, dirty, ready, cacheKey, status, conflicts]);
  function restoreConflict() {
    const conflict = conflicts[0];
    if (!conflict) return;
    // Preserve work typed while the conflict was awaiting a choice, too.
    setConflicts(items => [...items.slice(1), ...(dirty && (retainConflict?.(draft) ?? true) ? [{ base: baseline, draft }] : [])]);
    restore(conflict.draft);
    setRecovered(true);
  }
  useUnsaved(dirty || conflicts.length > 0);
  return { dirty, recovered, conflict: conflicts[0]?.draft, restoreConflict, discardConflict: () => setConflicts(items => items.slice(1)) };
}
async function fingerprint(value: object) {
  return sha256Bytes(new TextEncoder().encode(JSON.stringify(value)).buffer);
}
function DraftPreview({ snapshot, manuscript, onClose }: { snapshot: Snapshot; manuscript: Case; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <section className={s.snapshot} ref={ref} tabIndex={-1} aria-label={snapshot.kind === "invitation" ? "邀请草稿完整预览" : "决定信草稿完整预览"}>
    <div className={s.sectionHead}><h3>{snapshot.kind === "invitation" ? "邀请草稿预览" : "决定信草稿预览"}</h3><button type="button" onClick={onClose}>关闭预览</button></div>
    <p className={s.notice}>只读草稿，不构成审批。演示模式禁止发送邮件或发布正式决定。</p>
    <dl className={s.metadata}><div><dt>稿件</dt><dd>{manuscript.number} {manuscript.title}</dd></div><div><dt>收件人</dt><dd>{snapshot.to}</dd></div>{snapshot.due && <div><dt>审稿期限</dt><dd>{snapshot.due}</dd></div>}{snapshot.outcome && <div><dt>拟定结果</dt><dd>{outcomes[snapshot.outcome]}</dd></div>}<div><dt>主题</dt><dd>{snapshot.subject}</dd></div><div><dt>附件</dt><dd>无附件</dd></div></dl>
    <div className={s.letter}>{snapshot.body}</div>
    <details className={s.digest}><summary>核对快照依据</summary><p>准备前工作区修订 {snapshot.revision}。正文或收件人变更后需重新准备预览。</p><p>SHA-256：{snapshot.digest}</p></details>
  </section>;
}
function CandidateFacts({ candidate }: { candidate: Candidate }) {
  return <><dl className={s.metadata}><div><dt>研究方向</dt><dd>{candidate.topics.join("、")}</dd></div><div><dt>审稿记录</dt><dd>{candidate.review_history || "暂无记录，待核实"}</dd></div><div><dt>可用时间</dt><dd>{candidate.availability || "未提供，待核实"}</dd></div><div><dt>利益冲突</dt><dd>{candidate.conflict || "尚未核实"}</dd></div></dl>
    <h4>推荐依据</h4><p className={s.prose}>{candidate.reason}</p><h4>相关论文</h4><ul className={s.papers}>{candidate.papers.map((p, i) => <li key={`${p.title}-${i}`}><strong>{p.title}</strong><span>{p.year} · {p.source}</span></li>)}</ul><h4>来源</h4><ul className={s.sources}>{candidate.sources.map((source, i) => <li key={i}>{source}</li>)}</ul><p className={s.muted}>合成候选档案与论文，仅用于演示；履历、可用性与利益冲突尚未经外部核实。</p></>;
}

export function ReviewerSelection(props: Props) { return <ReviewerSelectionBody key={`${props.storageScope || "session"}:${props.manuscript.id}`} {...props} />; }
function ReviewerSelectionBody({ manuscript, state, onSave, storageScope, prepare, onDraftChange }: Props) {
  const saver = useSave(onSave);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("");
  const [activeId, setActiveId] = useState(manuscript.candidates[0]?.id || "");
  const [compare, setCompare] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(prepare === true);
  const [invitation, setInvitation] = useState(state.invitation);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [formError, setFormError] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const storageKey = `publishing-reviewer-view:${storageScope || "session"}:${manuscript.id}`;
  const ui = useRef({ query: "", topic: "", activeId, scroll: 0 });
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (raw) {
        const saved = JSON.parse(raw);
        queueMicrotask(() => {
          setQuery(typeof saved.query === "string" ? saved.query : "");
          setTopic(typeof saved.topic === "string" ? saved.topic : "");
          if (manuscript.candidates.some(c => c.id === saved.activeId)) setActiveId(saved.activeId);
          ui.current = { query: saved.query || "", topic: saved.topic || "", activeId: saved.activeId || "", scroll: Number(saved.scroll) || 0 };
          requestAnimationFrame(() => { if (list.current) list.current.scrollTop = ui.current.scroll; });
        });
      }
    } catch { /* UI restoration is optional when browser storage is unavailable. */ }
  }, [storageKey, manuscript.candidates]);
  function remember(next: Partial<typeof ui.current>) {
    ui.current = { ...ui.current, ...next };
    try { sessionStorage.setItem(storageKey, JSON.stringify(ui.current)); } catch { /* Browser privacy mode may disallow storage. */ }
  }
  const topics = [...new Set(manuscript.candidates.flatMap(c => c.topics))];
  const filtered = useMemo(() => manuscript.candidates.filter(c => (!topic || c.topics.includes(topic)) && `${c.name} ${c.affiliation} ${c.topics.join(" ")} ${c.papers.map(p => p.title).join(" ")}`.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim())), [manuscript.candidates, query, topic]);
  const active = filtered.find(c => c.id === activeId) || filtered[0];
  const activeIndex = active ? filtered.findIndex(c => c.id === active.id) : -1;
  const selected = manuscript.candidates.filter(c => state.selected_reviewers.includes(c.id));
  const recipients = selected.map(c => c.email).join(", ");
  const invitationDraft = useDraftPersistence({
    draft: invitation, saved: state.invitation, status: saver.status,
    cacheKey: storageScope ? `publishing-pending-invitation:${storageScope}:${manuscript.id}` : undefined,
    // Recipient metadata comes from the selected candidates, not a manual letter.
    retainConflict: value => Boolean(value.subject || value.body || value.due),
    restore: value => setInvitation({ ...value, to: recipients }),
    save: value => saver.save({ invitation: { ...value, to: recipients } }),
  });
  const dirty = invitationDraft.dirty;
  useEffect(() => { onDraftChange?.(dirty ? { invitation } : null); }, [dirty, invitation, onDraftChange]);
  useEffect(() => () => onDraftChange?.(null), [onDraftChange]);
  async function toggle(candidate: Candidate) {
    const ids = state.selected_reviewers.includes(candidate.id) ? state.selected_reviewers.filter(id => id !== candidate.id) : [...state.selected_reviewers, candidate.id];
    const to = manuscript.candidates.filter(c => ids.includes(c.id)).map(c => c.email).join(", ");
    const next = { ...invitation, to };
    if (await saver.save({ selected_reviewers: ids, invitation: next })) { setInvitation(current => ({ ...current, to })); setSnapshot(null); }
  }
  function editInvitation(key: keyof CaseState["invitation"], value: string) { setInvitation(draft => ({ ...draft, [key]: value })); setSnapshot(null); }
  async function saveInvitation(preview: boolean) {
    setFormError("");
    if (!selected.length || selected.some(c => !/^[^\s@]+@[^\s@]+\.test$/.test(c.email))) { setFormError("请先选择具有 .test 演示地址的候选人。"); return; }
    if (preview && (!invitation.subject.trim() || !invitation.body.trim() || !invitation.due)) { setFormError("请填写邀请主题、正文和审稿期限后准备预览。"); return; }
    const draft = { ...invitation, to: recipients };
    if (!(await saver.save({ invitation: draft }))) return;
    setInvitation(current => JSON.stringify(current) === JSON.stringify(invitation) ? draft : current);
    if (preview) {
      const value = { kind: "invitation" as const, ...draft, revision: state.revision };
      setSnapshot({ ...value, digest: await fingerprint(value) });
    }
  }
  function openInvitation() {
    setInviteOpen(true);
    setInvitation(d => ({ ...d, to: recipients, subject: d.subject || `审稿邀请：${manuscript.number} ${manuscript.title}`, body: d.body || `尊敬的审稿人：\n\n诚邀您评审稿件《${manuscript.title}》（${manuscript.number}）。\n\n请核实您与作者及相关机构是否存在利益冲突，并告知是否能够在约定期限内完成审稿。\n\n感谢您对同行评审工作的支持。\n编辑部` }));
  }
  return <section className={s.page} aria-label="审稿人选择">
    <header className={s.header}><div><h2>选择审稿人</h2><p className={s.muted}>{manuscript.number} · {manuscript.title}</p></div><div className={s.actions}><button type="button" disabled={selected.length < 2} aria-pressed={compare} onClick={() => setCompare(!compare)}>{compare ? "关闭比较" : `比较已选（${selected.length}）`}</button><button type="button" className={s.primary} disabled={!selected.length} onClick={openInvitation}>准备邀请</button></div></header>
    <div className={s.toolbar}><label className={s.search}>搜索候选人<input name="reviewer-search" type="search" autoComplete="off" placeholder="姓名、机构、研究方向…" value={query} onChange={e => { setQuery(e.target.value); remember({ query: e.target.value, scroll: 0 }); }} /></label><label>研究方向<select name="reviewer-topic" value={topic} onChange={e => { setTopic(e.target.value); remember({ topic: e.target.value, scroll: 0 }); }}><option value="">全部方向</option>{topics.map(t => <option key={t}>{t}</option>)}</select></label><span className={s.count}>{filtered.length} 位候选 · 已选 {selected.length} 位</span></div>
    <Feedback saver={saver} />
    {invitationDraft.conflict && <section className={s.notice} aria-label="本地邀请草稿冲突"><p role="status">服务器草稿已更新，本地未保存的草稿仍可恢复。</p><details><summary>查看本地草稿</summary><dl className={s.metadata}><div><dt>收件人</dt><dd>{invitationDraft.conflict.to || "未选择"}</dd></div><div><dt>主题</dt><dd>{invitationDraft.conflict.subject || "未填写"}</dd></div><div><dt>审稿期限</dt><dd>{invitationDraft.conflict.due || "未填写"}</dd></div></dl><div className={s.letter}>{invitationDraft.conflict.body || "正文为空"}</div></details><div className={s.actions}><button type="button" disabled={saver.status === "saving"} onClick={() => { invitationDraft.restoreConflict(); setInviteOpen(true); setSnapshot(null); }}>恢复本地草稿</button><button type="button" onClick={() => { if (window.confirm("丢弃这份本地草稿？服务器草稿将保留。")) invitationDraft.discardConflict(); }}>丢弃本地草稿</button></div></section>}
    <div className={s.reviewerLayout}><div className={s.candidateList} ref={list} onScroll={e => remember({ scroll: e.currentTarget.scrollTop })}>
      {filtered.length ? <table className={s.table}><thead><tr><th scope="col">选择</th><th scope="col">候选人</th><th scope="col">可用时间</th></tr></thead><tbody>{filtered.map(c => <tr key={c.id} className={active?.id === c.id ? s.activeRow : undefined}><td><label className={s.check}><input type="checkbox" checked={state.selected_reviewers.includes(c.id)} disabled={saver.status === "saving"} onChange={() => void toggle(c)} aria-label={`选择 ${c.name}`} /></label></td><td><button type="button" className={s.candidateName} aria-pressed={active?.id === c.id} onClick={() => { setActiveId(c.id); remember({ activeId: c.id }); }}>{c.name}</button><div className={s.muted}>{c.affiliation}</div><div className={s.topicText}>{c.topics.join(" · ")}</div></td><td>{c.availability || "待核实"}</td></tr>)}</tbody></table> : <div className={s.empty}><h3>没有符合条件的候选人</h3><button type="button" onClick={() => { setQuery(""); setTopic(""); remember({ query: "", topic: "" }); }}>清除筛选</button></div>}
    </div><aside className={s.candidatePreview} aria-label="候选人预览">{active ? <><div className={s.previewNav}><button type="button" disabled={activeIndex <= 0} onClick={() => { const id = filtered[activeIndex - 1].id; setActiveId(id); remember({ activeId: id }); }}>上一位</button><span>{activeIndex + 1} / {filtered.length}</span><button type="button" disabled={activeIndex >= filtered.length - 1} onClick={() => { const id = filtered[activeIndex + 1].id; setActiveId(id); remember({ activeId: id }); }}>下一位</button></div><h3>{active.name}</h3><p className={s.muted}>{active.affiliation}</p><CandidateFacts candidate={active} /></> : <p className={s.muted}>调整筛选后查看候选人资料。</p>}</aside></div>
    {compare && <section className={s.compare} aria-label="已选候选人比较"><div className={s.sectionHead}><h3>比较已选候选人</h3><button type="button" onClick={() => setCompare(false)}>关闭比较</button></div>{selected.length < 2 ? <p>至少选择两位候选人进行比较。</p> : <div className={s.compareGrid}>{selected.map(c => <article key={c.id}><h3>{c.name}</h3><p className={s.muted}>{c.affiliation}</p><CandidateFacts candidate={c} /></article>)}</div>}</section>}
    {inviteOpen && <section className={s.formSection} aria-label="邀请草稿"><div className={s.sectionHead}><h3>邀请草稿</h3><span className={s.muted}>对外通信草稿 · 尚未发送</span></div><form onSubmit={e => { e.preventDefault(); void saveInvitation(true); }}><label>收件人<input name="invitation-to" type="text" value={recipients} readOnly spellCheck={false} /><span className={s.muted}>由已选候选人的演示地址组成。</span></label><label>稿件<input name="invitation-manuscript" value={`${manuscript.number} ${manuscript.title}`} readOnly /></label><div className={s.formRow}><label>主题<input name="invitation-subject" autoComplete="off" value={invitation.subject} onChange={e => editInvitation("subject", e.target.value)} /></label><label>审稿期限<input name="invitation-due" type="date" value={invitation.due} onChange={e => editInvitation("due", e.target.value)} /></label></div><label>邀请正文<textarea name="invitation-body" rows={10} value={invitation.body} onChange={e => editInvitation("body", e.target.value)} /></label>{formError && <p className={s.error} role="alert">{formError}</p>}<div className={s.actions}><button type="button" disabled={saver.status === "saving"} onClick={() => void saveInvitation(false)}>保存邀请草稿</button><button className={s.primary} disabled={saver.status === "saving"} type="submit">保存并查看完整预览</button><span className={s.muted}>{dirty ? "草稿待保存" : invitationDraft.recovered ? "已恢复草稿" : "草稿已与工作区同步"}</span></div></form></section>}
    {snapshot && <DraftPreview snapshot={snapshot} manuscript={manuscript} onClose={() => setSnapshot(null)} />}
  </section>;
}

export function RevisionDesk(props: Props) { return <RevisionDeskBody key={`${props.storageScope || "session"}:${props.manuscript.id}`} {...props} />; }
function RevisionDeskBody({ manuscript, state, onSave, onEvidence, storageScope, prepare, onDraftChange }: Props) {
  const saver = useSave(onSave);
  const [round, setRound] = useState(manuscript.rounds.at(-1)?.number || 1);
  const [preparing, setPreparing] = useState(prepare === true);
  const [decision, setDecision] = useState(state.decision);
  const [notes, setNotes] = useState(state.notes);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [formError, setFormError] = useState("");
  const issues = manuscript.issues.filter(issue => issue.round === round);
  const currentRound = manuscript.rounds.find(r => r.number === round);
  const unresolved = manuscript.issues.filter(i => (state.issue_statuses[i.id] || i.initial_status) !== "resolved" && (state.issue_statuses[i.id] || i.initial_status) !== "ignored");
  const ongoing = manuscript.rounds.flatMap(r => r.tasks.filter(t => !["已完成", "已提交", "已提交意见", "completed", "submitted", "received"].includes(t.status)).map(t => ({ ...t, round: r.number })));
  const revisionDraft = useDraftPersistence({
    draft: { decision, notes }, saved: { decision: state.decision, notes: state.notes }, status: saver.status,
    cacheKey: storageScope ? `publishing-pending-decision:${storageScope}:${manuscript.id}` : undefined,
    restore: value => { setDecision(value.decision); setNotes(value.notes); },
    save: value => saver.save(value),
  });
  const dirty = revisionDraft.dirty;
  useEffect(() => { onDraftChange?.(dirty ? { decision, notes } : null); }, [dirty, decision, notes, onDraftChange]);
  useEffect(() => () => onDraftChange?.(null), [onDraftChange]);
  async function saveDecision(preview: boolean) {
    setFormError("");
    if (preview && (!decision.outcome || !decision.body.trim())) { setFormError("请选择拟定结果并填写决定信正文后查看预览。"); return; }
    if (!(await saver.save({ decision, notes }))) return;
    if (preview) {
      const value = { kind: "decision" as const, to: manuscript.authors.join("、") + "（作者；未配置发送地址）", subject: `${manuscript.number} 编辑决定草稿`, body: decision.body, outcome: decision.outcome, revision: state.revision };
      setSnapshot({ ...value, digest: await fingerprint(value) });
    }
  }
  function editDecision(key: keyof CaseState["decision"], value: string) { setDecision(d => ({ ...d, [key]: value })); setSnapshot(null); }
  return <section className={s.page} aria-label="修回核验与编辑决定"><header className={s.header}><div><h2>修回核验</h2><p className={s.muted}>{manuscript.number} · {manuscript.title}</p></div><div className={s.actions}><label className={s.inlineLabel}>审稿轮次<select name="review-round" value={round} onChange={e => setRound(Number(e.target.value))}>{manuscript.rounds.map(r => <option key={r.number} value={r.number}>{r.label}</option>)}</select></label><button type="button" className={s.primary} onClick={() => setPreparing(true)}>准备编辑决定</button></div></header><Feedback saver={saver} />
    {revisionDraft.conflict && <section className={s.notice} aria-label="本地决定草稿冲突"><p role="status">服务器草稿已更新，本地未保存的草稿仍可恢复。</p><details><summary>查看本地草稿</summary><dl className={s.metadata}><div><dt>拟定结果</dt><dd>{outcomes[revisionDraft.conflict.decision.outcome] || "未选择"}</dd></div></dl><div className={s.letter}>{revisionDraft.conflict.decision.body || "决定信正文为空"}</div><h4>内部编辑笔记</h4><div className={s.letter}>{revisionDraft.conflict.notes || "笔记为空"}</div></details><div className={s.actions}><button type="button" disabled={saver.status === "saving"} onClick={() => { revisionDraft.restoreConflict(); setPreparing(true); setSnapshot(null); }}>恢复本地草稿</button><button type="button" onClick={() => { if (window.confirm("丢弃这份本地草稿？服务器草稿将保留。")) revisionDraft.discardConflict(); }}>丢弃本地草稿</button></div></section>}
    <div className={s.issueSummary}><strong>{currentRound?.label || `第 ${round} 轮`}</strong><span>{issues.length} 项核验</span><span>状态为合成稿件的人工核验记录</span></div>
    <div className={s.issues}>{issues.length ? issues.map(issue => <article key={issue.id} className={s.issue}><div className={s.sectionHead}><h3>{issue.title}</h3><label className={s.inlineLabel}>核验状态<select name={`issue-status-${issue.id}`} aria-label={`${issue.title}核验状态`} value={state.issue_statuses[issue.id] || issue.initial_status} disabled={saver.status === "saving"} onChange={e => { setSnapshot(null); void saver.save({ issue_statuses: { ...state.issue_statuses, [issue.id]: e.target.value } }); }}>{["unanswered", "unverified", "resolved", "ignored"].map(status => <option key={status} value={status}>{issueLabels[status]}</option>)}</select></label></div><p className={s.issueOrigin}>{issue.source} · {issue.visibility === "internal" ? "仅编辑部可见" : "提供给作者的意见"}</p><div className={s.responseGrid}><section><h4>审稿意见</h4><p className={s.prose}>{issue.comment}</p></section><section><h4>作者回复</h4><p className={s.prose}>{issue.response || "作者尚未回复。"}</p></section></div><div className={s.diff}><section className={s.before}><div className={s.diffHead}><h4>原稿 · {issue.before.version}</h4>{onEvidence && <button type="button" onClick={() => onEvidence(issue.before)}>查看原文</button>}</div><p>{issue.before.quote}</p><span className={s.muted}>{issue.before.section} · {issue.before.location}</span></section><section className={s.after}><div className={s.diffHead}><h4>修订稿 · {issue.after.version}</h4>{onEvidence && <button type="button" onClick={() => onEvidence(issue.after)}>定位修改</button>}</div><p>{issue.after.quote}</p><span className={s.muted}>{issue.after.section} · {issue.after.location}</span></section></div></article>) : <div className={s.empty}>本轮暂无问题记录。</div>}</div>
    <section className={s.notes}><label htmlFor={`editor-notes-${manuscript.id}`}>内部编辑笔记</label><textarea id={`editor-notes-${manuscript.id}`} name="editor-notes" rows={4} placeholder="记录核验依据，仅编辑部可见…" value={notes} onChange={e => setNotes(e.target.value)} /><div className={s.actions}><button type="button" disabled={saver.status === "saving"} onClick={() => void saver.save({ notes })}>保存内部笔记</button><span className={s.muted}>{revisionDraft.recovered ? "已恢复草稿 · " : ""}仅本人工作区，不提供给作者</span></div></section>
    {preparing && <section className={s.decision} aria-label="编辑决定准备"><div className={s.sectionHead}><h3>准备编辑决定</h3><span className={s.muted}>草稿 · 未发布</span></div><p className={s.notice}>准备决定不会取消审稿任务。正式发布与外发在演示模式中禁用。</p><div className={s.decisionContext}><section><h4>已收到的意见</h4>{manuscript.issues.length ? <ul className={s.reportList}>{manuscript.issues.map(i => <li key={i.id}><span>第 {i.round} 轮 · {i.source}</span><strong>{i.title}</strong><p>{i.comment}</p></li>)}</ul> : <p>尚无审稿意见。</p>}</section><section><h4>未完成事项（{unresolved.length}）</h4>{unresolved.length ? <ul className={s.taskList}>{unresolved.map(i => <li key={i.id}><strong>{i.title}</strong><span>第 {i.round} 轮 · {issueLabels[state.issue_statuses[i.id] || i.initial_status]}</span></li>)}</ul> : <p>当前问题均已处理。</p>}<h4>仍在进行的审稿任务（{ongoing.length}）</h4>{ongoing.length ? <ul className={s.taskList}>{ongoing.map((task, i) => <li key={`${task.round}-${i}`}><strong>{task.reviewer}</strong><span>第 {task.round} 轮 · {task.status} · 期限 {task.due}</span></li>)}</ul> : <p>当前没有进行中的审稿任务。</p>}</section></div><form onSubmit={e => { e.preventDefault(); void saveDecision(true); }}><label>拟定结果<select name="decision-outcome" value={decision.outcome} onChange={e => editDecision("outcome", e.target.value)}><option value="">请选择结果</option>{Object.entries(outcomes).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label><label>决定信正文<textarea name="decision-body" rows={12} placeholder="填写拟提供给作者的完整决定信…" value={decision.body} onChange={e => editDecision("body", e.target.value)} /></label>{formError && <p className={s.error} role="alert">{formError}</p>}<div className={s.actions}><button type="button" disabled={saver.status === "saving"} onClick={() => void saveDecision(false)}>保存决定草稿</button><button type="submit" className={s.primary} disabled={saver.status === "saving"}>保存并查看决定信预览</button><span className={s.muted}>{dirty ? "草稿待保存" : revisionDraft.recovered ? "已恢复草稿" : "草稿已与工作区同步"}</span></div></form></section>}
    {snapshot && <DraftPreview snapshot={snapshot} manuscript={manuscript} onClose={() => setSnapshot(null)} />}
  </section>;
}
