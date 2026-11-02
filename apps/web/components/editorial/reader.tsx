"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import type { Anchor, Case, CaseState, PatchState, View } from "./types";
import styles from "./reader.module.css";

type Props = { manuscript: Case; state: CaseState; onSave: PatchState; onNavigate: (view: View) => void; anchor?: Anchor; storageScope?: string };
type ReadingPosition = { version: string; section: string; paragraph: number };
type PendingNote = { text: string; base_note: string; base_revision: number };
const noteCacheKey = (scope: string, caseId: string, versionId: string) => `publishing-os-pending-note:${encodeURIComponent(scope)}:${encodeURIComponent(caseId)}:${encodeURIComponent(versionId)}`;
function cacheNote(scope: string | undefined, caseId: string, versionId: string, note: PendingNote) {
  if (!scope) return;
  try { sessionStorage.setItem(noteCacheKey(scope, caseId, versionId), JSON.stringify(note)); } catch { /* The visible draft remains available if session storage is full or disabled. */ }
}
function removeCachedNote(scope: string | undefined, caseId: string, versionId: string, text: string) {
  if (!scope) return;
  try {
    const key = noteCacheKey(scope, caseId, versionId);
    const current = JSON.parse(sessionStorage.getItem(key) || "null");
    if (current?.text === text) sessionStorage.removeItem(key);
  } catch { /* A storage failure must not undo a successful backend save. */ }
}

type ReaderPrefs = { font: number; width: number; toc: boolean; panel: boolean; focus: boolean };
const defaults: ReaderPrefs = { font: 17, width: 328, toc: true, panel: true, focus: false };
const preferenceKey = "publishing-os-reader-preferences";
const boundedWidth = (width: number) => Math.min(480, Math.max(264, width));

function Highlight({ text, quote }: { text: string; quote?: string }) {
  const index = quote ? text.indexOf(quote) : -1;
  if (index < 0 || !quote) return <>{text}</>;
  return <>{text.slice(0, index)}<mark>{quote}</mark>{text.slice(index + quote.length)}</>;
}

export default function Reader({ manuscript, state, onSave, onNavigate, anchor, storageScope }: Props) {
  const firstVersion = manuscript.versions.find(v => v.id === state.reading.version) ?? manuscript.versions.at(-1)!;
  const [versionId, setVersionId] = useState(firstVersion.id);
  const [sectionId, setSectionId] = useState(state.reading.section || firstVersion.sections[0]?.id || "");
  const [prefs, setPrefs] = useState<ReaderPrefs>(defaults);
  const [prefsReady, setPrefsReady] = useState(false);
  const [panelTab, setPanelTab] = useState<"issues" | "notes">("issues");
  const [drafts, setDrafts] = useState<Record<string, string>>(state.version_notes ?? {});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  const [target, setTarget] = useState<Anchor | undefined>(anchor);
  const [notice, setNotice] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const saveRef = useRef(onSave);
  const stateRef = useRef(state);
  const draftsRef = useRef(drafts);
  const dirtyNotes = useRef(false);
  const pendingNotes = useRef<Record<string, PendingNote>>({});
  const noteTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const readingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const retryPatch = useRef<Partial<Omit<CaseState, "revision">> | undefined>(undefined);
  const pending = useRef(0);
  const restoreSection = useRef(state.reading.section);
  const restoreParagraph = useRef(state.reading.paragraph ?? 0);
  const lastReading = useRef<ReadingPosition>({ version: firstVersion.id, section: state.reading.section || firstVersion.sections[0]?.id || "", paragraph: state.reading.paragraph ?? 0 });
  const pendingReading = useRef<ReadingPosition | undefined>(undefined);
  const version = manuscript.versions.find(v => v.id === versionId) ?? firstVersion;
  const originalUrl = (file: string) => `/api/editorial-demo/cases/${encodeURIComponent(manuscript.id)}/files/${encodeURIComponent(file)}`;

  useEffect(() => {
    saveRef.current = onSave;
    stateRef.current = state;
    for (const [id, note] of Object.entries(pendingNotes.current)) {
      if ((state.version_notes[id] ?? "") !== note.base_note) continue;
      const rebased = { ...note, base_revision: state.revision };
      pendingNotes.current[id] = rebased;
      cacheNote(storageScope, manuscript.id, id, rebased);
    }
  }, [onSave, state, storageScope, manuscript.id]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      try {
        const stored = JSON.parse(localStorage.getItem(preferenceKey) || "null");
        if (stored) setPrefs({ font: [16, 17, 18].includes(stored.font) ? stored.font : 17, width: boundedWidth(Number(stored.width) || 328), toc: stored.toc !== false, panel: stored.panel !== false, focus: stored.focus === true });
      } catch { /* Unavailable local preferences do not prevent reading. */ }
      setPrefsReady(true);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (!prefsReady) return;
    try { localStorage.setItem(preferenceKey, JSON.stringify(prefs)); } catch { /* Reading remains usable in private storage modes. */ }
  }, [prefs, prefsReady]);

  const persist = useCallback(async (patch: Partial<Omit<CaseState, "revision">>) => {
    pending.current += 1;
    setSaving(true);
    setSaved(false);
    try {
      await saveRef.current(patch);
      if (patch.reading && pendingReading.current?.version === patch.reading.version && pendingReading.current?.section === patch.reading.section && pendingReading.current?.paragraph === (patch.reading.paragraph ?? 0)) pendingReading.current = undefined;
      if (patch.version_notes) {
        for (const [id, text] of Object.entries(patch.version_notes)) {
          removeCachedNote(storageScope, manuscript.id, id, text);
          const note = pendingNotes.current[id];
          if (!note) continue;
          if (note.text === text) delete pendingNotes.current[id];
          else {
            // A successful older save becomes the base for the newer in-flight edit.
            const rebased = { ...note, base_note: text, base_revision: Math.max(note.base_revision, stateRef.current.revision) };
            pendingNotes.current[id] = rebased;
            cacheNote(storageScope, manuscript.id, id, rebased);
          }
        }
        dirtyNotes.current = Object.keys(pendingNotes.current).length > 0;
      }
      const unresolved = { ...retryPatch.current };
      for (const key of Object.keys(patch)) delete unresolved[key as keyof typeof unresolved];
      retryPatch.current = Object.keys(unresolved).length ? unresolved : undefined;
      setSaveError(retryPatch.current ? "保存失败，未保存笔记已保留，可重试。" : "");
      setSaved(!retryPatch.current && !dirtyNotes.current);
    } catch {
      retryPatch.current = { ...retryPatch.current, ...patch };
      setSaveError("保存失败，未保存笔记已保留，可重试。");
    } finally {
      pending.current -= 1;
      setSaving(pending.current > 0);
    }
  }, [manuscript.id, storageScope]);

  const flushNotes = useCallback(() => {
    if (noteTimer.current) clearTimeout(noteTimer.current);
    if (!dirtyNotes.current) return;
    const changes = Object.fromEntries(Object.entries(pendingNotes.current).map(([id, note]) => [id, note.text]));
    void persist({ version_notes: { ...(stateRef.current.version_notes ?? {}), ...changes } });
  }, [persist]);

  useEffect(() => {
    if (!storageScope) return;
    const frame = requestAnimationFrame(() => {
      const restored: Record<string, string> = {};
      for (const item of manuscript.versions) {
        const key = noteCacheKey(storageScope, manuscript.id, item.id);
        try {
          const note: PendingNote | null = JSON.parse(sessionStorage.getItem(key) || "null");
          if (!note) continue;
          const current = stateRef.current;
          if (typeof note.text !== "string" || note.text.length > 10000 || typeof note.base_note !== "string" || !Number.isInteger(note.base_revision) || note.base_note !== (current.version_notes[item.id] ?? "")) {
            sessionStorage.removeItem(key);
            continue;
          }
          if (note.text === (current.version_notes[item.id] ?? "")) {
            sessionStorage.removeItem(key);
            continue;
          }
          pendingNotes.current[item.id] = note;
          restored[item.id] = note.text;
        } catch { /* Invalid cache entries never override backend state. */ }
      }
      if (!Object.keys(restored).length) return;
      draftsRef.current = { ...draftsRef.current, ...restored };
      dirtyNotes.current = true;
      setDrafts(draftsRef.current);
      setNotice("已恢复未保存的版本笔记，正在重新保存。");
      noteTimer.current = setTimeout(flushNotes, 650);
    });
    return () => cancelAnimationFrame(frame);
  }, [storageScope, manuscript.id, manuscript.versions, flushNotes]);

  useEffect(() => () => {
    if (noteTimer.current) clearTimeout(noteTimer.current);
    if (readingTimer.current) clearTimeout(readingTimer.current);
    if (dirtyNotes.current || pendingReading.current) {
      const changes = Object.fromEntries(Object.entries(pendingNotes.current).map(([id, note]) => [id, note.text]));
      const patch: Partial<Omit<CaseState, "revision">> = {};
      if (dirtyNotes.current) patch.version_notes = { ...(stateRef.current.version_notes ?? {}), ...changes };
      if (pendingReading.current) patch.reading = pendingReading.current;
      void saveRef.current(patch).then(() => {
        for (const [id, text] of Object.entries(changes)) removeCachedNote(storageScope, manuscript.id, id, text);
      }).catch(() => undefined);
    }
  }, [storageScope, manuscript.id]);

  useEffect(() => {
    const warnUnsaved = (event: BeforeUnloadEvent) => {
      if (!dirtyNotes.current && !pending.current && !retryPatch.current) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnUnsaved);
    return () => window.removeEventListener("beforeunload", warnUnsaved);
  }, []);

  const scrollArticleTo = useCallback((element: Element | null | undefined, centered = false) => {
    const container = scrollRef.current;
    if (!container || !element) return;
    const bounds = element.getBoundingClientRect();
    const offset = centered ? Math.max(24, (container.clientHeight - bounds.height) / 2) : 24;
    const top = bounds.top - container.getBoundingClientRect().top + container.scrollTop - offset;
    container.scrollTo({ top: Math.max(0, top), behavior: "instant" });
  }, []);

  const jump = useCallback((destination: Anchor) => {
    if (readingTimer.current) clearTimeout(readingTimer.current);
    flushNotes();
    setVersionId(destination.version);
    setSectionId(destination.section);
    setTarget(destination);
    restoreSection.current = destination.section;
    const sourceSection = manuscript.versions.find(item => item.id === destination.version)?.sections.find(item => item.id === destination.section);
    const paragraph = Math.max(0, sourceSection?.paragraphs.findIndex(text => text.includes(destination.quote)) ?? 0);
    restoreParagraph.current = paragraph;
    const position = { version: destination.version, section: destination.section, paragraph };
    lastReading.current = position;
    pendingReading.current = position;
    void persist({ reading: position });
    requestAnimationFrame(() => {
      const highlighted = scrollRef.current?.querySelector("mark");
      scrollArticleTo(highlighted ?? sectionRefs.current[destination.section], Boolean(highlighted));
    });
  }, [flushNotes, persist, scrollArticleTo, manuscript.versions]);

  useEffect(() => {
    if (!anchor) return;
    const frame = requestAnimationFrame(() => jump(anchor));
    return () => cancelAnimationFrame(frame);
  }, [anchor, jump]);

  useEffect(() => {
    const section = target?.version === versionId ? target.section : restoreSection.current;
    const frame = requestAnimationFrame(() => {
      const highlighted = target?.version === versionId ? scrollRef.current?.querySelector("mark") : undefined;
      const paragraph = sectionRefs.current[section]?.querySelectorAll(":scope > p")[restoreParagraph.current];
      if (highlighted) scrollArticleTo(highlighted, true);
      else if (restoreParagraph.current > 0 && paragraph) scrollArticleTo(paragraph);
      else if (section && section !== version.sections[0]?.id) scrollArticleTo(sectionRefs.current[section]);
      else if (scrollRef.current) scrollRef.current.scrollTo({ top: 0, behavior: "instant" });
    });
    return () => cancelAnimationFrame(frame);
  }, [versionId, target, version.sections, scrollArticleTo]);

  const rememberPosition = (id: string, paragraph: number) => {
    const previous = lastReading.current;
    if (previous.version === versionId && previous.section === id && previous.paragraph === paragraph) return;
    const position = { version: versionId, section: id, paragraph };
    lastReading.current = position;
    pendingReading.current = position;
    if (id !== sectionId) setSectionId(id);
    if (readingTimer.current) clearTimeout(readingTimer.current);
    readingTimer.current = setTimeout(() => { void persist({ reading: position }); }, 800);
  };

  const onScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const top = container.getBoundingClientRect().top;
    let current = version.sections[0]?.id;
    for (const section of version.sections) {
      const node = sectionRefs.current[section.id];
      if (node && node.getBoundingClientRect().top <= top + 32) current = section.id;
    }
    if (current) {
      let paragraph = 0;
      const paragraphs = sectionRefs.current[current]?.querySelectorAll(":scope > p");
      paragraphs?.forEach((node, index) => { if (node.getBoundingClientRect().top <= top + 32) paragraph = index; });
      rememberPosition(current, paragraph);
    }
  };

  const changeVersion = (id: string) => {
    flushNotes();
    if (readingTimer.current) clearTimeout(readingTimer.current);
    const next = manuscript.versions.find(v => v.id === id)!;
    const first = next.sections[0]?.id ?? "";
    restoreSection.current = first;
    restoreParagraph.current = 0;
    setVersionId(id);
    setSectionId(first);
    setTarget(undefined);
    setNotice("已切换阅读版本。已有核验记录保留；AI 结果按关联版本显示。");
    const position = { version: id, section: first, paragraph: 0 };
    lastReading.current = position;
    pendingReading.current = position;
    void persist({ reading: position });
  };

  const goSection = (id: string) => {
    restoreSection.current = id;
    restoreParagraph.current = 0;
    setTarget(undefined);
    setSectionId(id);
    scrollArticleTo(sectionRefs.current[id]);
    if (readingTimer.current) clearTimeout(readingTimer.current);
    if (version.sections.some(section => section.id === id)) {
      const position = { version: versionId, section: id, paragraph: 0 };
      lastReading.current = position;
      pendingReading.current = position;
      void persist({ reading: position });
    }
  };

  const resize = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = prefs.width;
    event.currentTarget.setPointerCapture(event.pointerId);
    const move = (next: globalThis.PointerEvent) => setPrefs(p => ({ ...p, width: boundedWidth(startWidth + startX - next.clientX) }));
    const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); window.removeEventListener("pointercancel", stop); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
  };
  const resizeKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const change = event.key === "ArrowLeft" ? 16 : event.key === "ArrowRight" ? -16 : 0;
    if (change) { event.preventDefault(); setPrefs(p => ({ ...p, width: boundedWidth(p.width + change) })); }
    if (event.key === "Home" || event.key === "End") { event.preventDefault(); setPrefs(p => ({ ...p, width: event.key === "Home" ? 264 : 480 })); }
  };
  const updateNotes = (text: string) => {
    const next = { ...draftsRef.current, [versionId]: text };
    draftsRef.current = next;
    setDrafts(next);
    const entry = { ...(pendingNotes.current[versionId] ?? { base_note: stateRef.current.version_notes[versionId] ?? "", base_revision: stateRef.current.revision }), text };
    pendingNotes.current[versionId] = entry;
    cacheNote(storageScope, manuscript.id, versionId, entry);
    dirtyNotes.current = true;
    setSaved(false);
    if (noteTimer.current) clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(flushNotes, 650);
  };
  const visiblePanel = prefs.panel && !prefs.focus;
  const visibleToc = prefs.toc && !prefs.focus;
  const round = manuscript.rounds.at(-1);

  return <div className={`${styles.reader} ${prefs.focus ? styles.focusMode : ""}`} style={{ "--reader-font": `${prefs.font}px`, "--reader-panel": `${prefs.width}px` } as CSSProperties}>
    <div className={styles.toolbar} aria-label="阅读设置">
      <div className={styles.toolbarGroup}>
        <button type="button" aria-expanded={visibleToc} aria-controls="reader-toc" onClick={() => setPrefs(p => ({ ...p, toc: !visibleToc, focus: false }))}>目录</button>
        <label className={styles.versionLabel}>版本<select aria-label="稿件版本" value={versionId} onChange={event => changeVersion(event.target.value)}>{manuscript.versions.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <a href={originalUrl(version.original)} download>下载原稿</a>
      </div>
      <div className={styles.toolbarGroup}>
        <label className={styles.fontLabel}>字号<select aria-label="正文字号" value={prefs.font} onChange={event => setPrefs(p => ({ ...p, font: Number(event.target.value) }))}>{[16, 17, 18].map(size => <option key={size} value={size}>{size}</option>)}</select></label>
        <button type="button" aria-pressed={prefs.focus} onClick={() => setPrefs(p => ({ ...p, focus: !p.focus }))}>{prefs.focus ? "退出专注" : "专注阅读"}</button>
        <button type="button" aria-expanded={visiblePanel} aria-controls="reader-evidence" onClick={() => setPrefs(p => ({ ...p, panel: !visiblePanel, focus: false }))}>问题与笔记</button>
      </div>
    </div>
    {notice && <div className={styles.notice} role="status">{notice}<button type="button" aria-label="关闭版本提示" onClick={() => setNotice("")}>关闭</button></div>}
    {saveError && <div className={styles.saveError} role="alert">{saveError}<button type="button" onClick={() => { if (retryPatch.current) {
      const retry = { ...retryPatch.current };
      if (retry.reading && pendingReading.current) retry.reading = pendingReading.current;
      if (retry.version_notes) retry.version_notes = { ...stateRef.current.version_notes, ...Object.fromEntries(Object.entries(pendingNotes.current).map(([id, note]) => [id, note.text])) };
      void persist(retry);
    } }}>重试保存</button></div>}
    <div className={`${styles.layout} ${visibleToc ? styles.withToc : ""} ${visiblePanel ? styles.withPanel : ""}`}>
      {visibleToc && <nav id="reader-toc" className={styles.toc} aria-label="稿件章节">
        <div className={styles.tocHeading}>本文目录</div>
        {version.sections.map(section => <button type="button" key={section.id} aria-current={sectionId === section.id ? "location" : undefined} onClick={() => goSection(section.id)}>{section.title}</button>)}
        <div className={styles.tocExtra}>
          <button type="button" onClick={() => goSection("reader-figures")}>图表 <span>{manuscript.figures.length}</span></button>
          <button type="button" onClick={() => goSection("reader-references")}>参考文献 <span>{manuscript.references.length}</span></button>
          <button type="button" onClick={() => goSection("reader-attachments")}>附件 <span>{manuscript.attachments.length}</span></button>
          <button type="button" onClick={() => goSection("reader-activity")}>沟通与历史 <span>{manuscript.history.length}</span></button>
        </div>
        <div className={styles.tocFooter}>{version.date}<br />{round?.label}</div>
      </nav>}
      <div className={styles.articleScroll} ref={scrollRef} onScroll={onScroll} tabIndex={0} aria-label="稿件正文">
        <article className={styles.article}>
          <header className={styles.articleHeader}>
            <h1>{manuscript.title}</h1>
            <p className={styles.englishTitle} lang="en">{manuscript.title_en}</p>
            <p className={styles.authors}>{manuscript.authors.join("，")}</p>
            <p className={styles.versionMeta}>{version.label}　{version.date}　合成演示稿件</p>
          </header>
          {version.sections.map(section => <section key={section.id} ref={node => { sectionRefs.current[section.id] = node; }} id={`article-${section.id}`} className={`${styles.articleSection} ${target?.version === versionId && target.section === section.id ? styles.targetSection : ""}`}>
            <h2>{section.title}</h2>
            {target?.version === versionId && target.section === section.id && <div className={styles.sourceLine}>定位原文：{target.location}<a href={originalUrl(target.file)} download>查看对应版本原稿</a></div>}
            {section.paragraphs.map((paragraph, index) => <p key={index}><Highlight text={paragraph} quote={target?.version === versionId && target.section === section.id ? target.quote : undefined} /></p>)}
          </section>)}
          <section ref={node => { sectionRefs.current["reader-figures"] = node; }} className={styles.articleSection}>
            <h2>图表</h2>
            {manuscript.figures.length ? manuscript.figures.map(figure => <figure key={figure.id} className={styles.figure}>
              <figcaption><strong>{figure.title}</strong><p>{figure.caption}</p></figcaption>
              <table><caption className={styles.srOnly}>{figure.title}数据</caption><thead><tr><th scope="col">项目</th><th scope="col">数值</th></tr></thead><tbody>{figure.values.map((value, index) => <tr key={index}><th scope="row">{value.label}</th><td>{value.value}</td></tr>)}</tbody></table>
              <div className={styles.formula}><span>合成图表数值核对</span><span role="math" aria-label="最大值减去最小值">Δ = max(x) − min(x) = {figure.values.length ? (Math.max(...figure.values.map(item => item.value)) - Math.min(...figure.values.map(item => item.value))).toFixed(1) : "0"}</span><small>由上表合成数据计算，仅辅助核对。</small></div>
            </figure>) : <p>此稿件没有图表。</p>}
          </section>
          <section ref={node => { sectionRefs.current["reader-references"] = node; }} className={styles.articleSection}>
            <h2>参考文献</h2>
            <ol className={styles.references}>{manuscript.references.map((reference, index) => <li key={index}>{reference}</li>)}</ol>
          </section>
          <section ref={node => { sectionRefs.current["reader-attachments"] = node; }} className={styles.articleSection}>
            <h2>附件与原始版本</h2>
            <ul className={styles.attachments}>{manuscript.attachments.map(file => <li key={file.id}><a href={originalUrl(file.id)} download>{file.name}</a><span>{manuscript.versions.find(v => v.id === file.version)?.label ?? file.version}</span></li>)}</ul>
          </section>
          <section ref={node => { sectionRefs.current["reader-activity"] = node; }} className={styles.articleSection}>
            <h2>沟通与操作历史</h2>
            {manuscript.rounds.length > 0 && <div className={styles.roundHistory}>{manuscript.rounds.map(item => <details key={item.number}><summary>{item.label}</summary>{item.tasks.map((task,index) => <p key={index}>{task.reviewer} — {task.status}；期限 {task.due}</p>)}</details>)}</div>}
            <ol className={styles.history}>{manuscript.history.map((item,index) => <li key={index}><div><strong>{item.actor}</strong><span>{item.visibility === "internal" ? "仅编辑内部" : "作者可见记录"}</span><time>{new Date(item.date).toLocaleString("zh-CN")}</time></div><p>{item.text}</p></li>)}</ol>
          </section>
          <footer className={styles.articleFooter}><span>已读至文末</span><button type="button" onClick={() => onNavigate("revision")}>核验修回与准备决定</button></footer>
        </article>
      </div>
      {visiblePanel && <>
        <div className={styles.separator} role="separator" aria-label="调整问题面板宽度" aria-orientation="vertical" aria-valuemin={264} aria-valuemax={480} aria-valuenow={prefs.width} tabIndex={0} onPointerDown={resize} onKeyDown={resizeKey} />
        <aside className={styles.panel} id="reader-evidence" aria-label="问题与编辑笔记">
          <div className={styles.panelTabs} role="tablist" aria-label="阅读辅助">
            <button type="button" role="tab" aria-selected={panelTab === "issues"} aria-controls="reader-issues" id="reader-issues-tab" tabIndex={panelTab === "issues" ? 0 : -1} onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "End"].includes(event.key)) { event.preventDefault(); setPanelTab("notes"); document.getElementById("reader-notes-tab")?.focus(); } }} onClick={() => setPanelTab("issues")}>问题 <span>{manuscript.issues.length}</span></button>
            <button type="button" role="tab" aria-selected={panelTab === "notes"} aria-controls="reader-notes" id="reader-notes-tab" tabIndex={panelTab === "notes" ? 0 : -1} onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) { event.preventDefault(); setPanelTab("issues"); document.getElementById("reader-issues-tab")?.focus(); } }} onClick={() => setPanelTab("notes")}>编辑笔记</button>
          </div>
          {panelTab === "issues" ? <div id="reader-issues" role="tabpanel" aria-labelledby="reader-issues-tab" className={styles.panelContent}>
            <p className={styles.panelScope}>{version.label} · 合成问题与证据</p>
            {manuscript.issues.length === 0 && <p className={styles.empty}>当前稿件没有待核验问题。可在右上角打开 AI 助手准备演示分析。</p>}
            {manuscript.issues.map(issue => {
              const result = state.ai_results.find(item => item.issue_id === issue.id && item.version === versionId);
              const isCurrent = issue.after.version === versionId || issue.before.version === versionId;
              return <section className={styles.issue} key={issue.id}>
                <div className={styles.issueMeta}><span>{issue.source} · 第 {issue.round} 轮</span><span className={styles.visibility}>{issue.visibility === "author" ? "提供给作者" : "仅编辑内部"}</span></div>
                <h3>{issue.title}</h3><p>{issue.comment}</p>
                <div className={styles.evidence}><div>原文依据</div><blockquote>{issue.before.quote}</blockquote><button type="button" onClick={() => jump(issue.before)}>{issue.before.version} · {issue.before.location}</button></div>
                <div className={styles.evidence}><div>修回位置</div><blockquote>{issue.after.quote}</blockquote><button type="button" onClick={() => jump(issue.after)}>{issue.after.version} · {issue.after.location}</button></div>
                {issue.response && <details className={styles.response}><summary>作者回复</summary><p>{issue.response}</p></details>}
                {!isCurrent && <p className={styles.stale}>此问题关联其他版本，请跳转后核验。</p>}
                {result && <div className={styles.aiResult}><p>AI 建议 · 演示</p><p>{result.text}</p><label>人工处理<select aria-label={`处理 AI 建议：${issue.title}`} value={result.status} onChange={event => { const value = event.target.value; void persist({ ai_results: state.ai_results.map(item => item.id === result.id ? { ...item, status: value } : item) }); }}><option value="pending">待核实</option><option value="adopted">采纳</option><option value="ignored">忽略</option></select></label></div>}
              </section>;
            })}
            <button type="button" className={styles.nextAction} onClick={() => onNavigate("revision")}>打开修回核验</button>
          </div> : <div id="reader-notes" role="tabpanel" aria-labelledby="reader-notes-tab" className={styles.notes}>
            <div className={styles.notesMeta}><span>{version.label}</span><span>仅编辑内部</span></div>
            <label htmlFor="editorial-version-notes">版本笔记</label>
            <textarea id="editorial-version-notes" value={drafts[versionId] ?? ""} onChange={event => updateNotes(event.target.value)} onBlur={flushNotes} placeholder="记录判断、待核实事项或后续处理…" maxLength={10000} autoComplete="off" name="version_notes" />
            <div className={styles.saveStatus} role="status">{saving ? "正在保存…" : saveError ? "尚未保存" : saved ? "已保存" : "自动保存至当前版本"}</div>
            <button type="button" onClick={flushNotes} disabled={saving}>保存笔记</button>
          </div>}
        </aside>
      </>}
    </div>
  </div>;
}
