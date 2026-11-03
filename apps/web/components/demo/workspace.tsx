"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import Glyph from "../editorial/icons";
import { answer, dateKey, hasReference, initialState, isDemoState, REFERENCE, STORAGE_KEY, welcome, type DemoState, type Manuscript, type Message } from "./data";
import s from "./workspace.module.css";

type Tab = "稿件" | "作者" | "证据";
const STEPS = ["投稿准备", "材料预审", "编辑初筛", "寻找审稿人", "同行评审", "作者修回", "制作校样"];
// Local demo identifiers carry no authentication/authorization semantics.
const id = () => globalThis.crypto.randomUUID?.() || Array.from(globalThis.crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join("-");

function Sheet({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className={s.dialog} onCancel={close} aria-label={title}>
    <div className={s.sheetHead}><strong>{title}</strong><button aria-label="关闭面板" onClick={close}><Glyph name="close" /></button></div>{children}
  </dialog>;
}

export default function DemoWorkspace() {
  const [state, setState] = useState<DemoState>(initialState);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("稿件");
  const [panel, setPanel] = useState<"tasks" | "material" | "about" | "new" | "reset" | null>(null);
  const [editing, setEditing] = useState(false);
  const [focusSource, setFocusSource] = useState("");
  const [sourceClick, setSourceClick] = useState(0);
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [dayFilter, setDayFilter] = useState("");
  const [notice, setNotice] = useState("");
  const [storageError, setStorageError] = useState(false);
  const [search, setSearch] = useState("");
  const transcript = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const selected = state.manuscripts.find(m => m.id === state.selected);
  const thread = selected?.id || "main";
  const messages = state.threads[thread] || [welcome(selected)];
  const draft = state.drafts[thread] || "";

  useEffect(() => {
    let restored: DemoState | null = null;
    let failed = false;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const value = JSON.parse(raw);
        if (isDemoState(value)) restored = value;
        else failed = true;
      }
    } catch { failed = true; }
    queueMicrotask(() => { if (restored) setState(restored); if (failed) setNotice("未能读取本地演示资料，已恢复初始样例。"); setReady(true); });
  }, []);

  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
    catch { queueMicrotask(() => setStorageError(true)); }
  }, [state, ready]);
  useEffect(() => { transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "instant" }); }, [messages.length, thread]);
  useEffect(() => {
    if (focusSource) Array.from(document.querySelectorAll<HTMLElement>("[data-demo-source]")).find(el => el.dataset.demoSource === focusSource && el.getClientRects().length)?.scrollIntoView({ block: "nearest" });
  }, [focusSource, sourceClick, tab, panel]);

  function choose(value: string) {
    setState(prev => ({ ...prev, selected: value })); setFocusSource(""); setEditing(false); setPanel(null); setTab("稿件");
  }
  function send(text = draft) {
    if (!text.trim() || !ready) return;
    const reply = answer(text.trim(), selected, state.manuscripts);
    setState(prev => ({ ...prev, drafts: { ...prev.drafts, [thread]: "" }, threads: { ...prev.threads, [thread]: [...(prev.threads[thread] || [welcome(selected)]), { id: id(), role: "user", text: text.trim() }, { ...reply, id: id(), evidence: selected ? Object.fromEntries(selected.paragraphs.map(p => [p.id, p.text])) : undefined }] } }));
  }
  function source(value: string) { setEditing(false); setTab(value === "external" ? "证据" : "稿件"); setFocusSource(value); setSourceClick(prev => prev+1); if (window.matchMedia("(max-width: 1050px)").matches) setPanel("material"); }
  function saveManuscript(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") || "").trim();
    const abstract = String(form.get("abstract") || "").trim();
    if (!title || !abstract) return;
    const authors = selected.authors.map((author, i) => ({ ...author, name: String(form.get(`name-${i}`) || "").trim(), affiliation: String(form.get(`affiliation-${i}`) || "").trim(), email: String(form.get(`email-${i}`) || "").trim(), orcid: String(form.get(`orcid-${i}`) || "").trim() }));
    setState(prev => ({ ...prev, manuscripts: prev.manuscripts.map(m => m.id === selected.id ? { ...m, title, short: title, abstract, authors, paragraphs: m.paragraphs.map(p => ({ ...p, text: p.id === "abstract" ? abstract : String(form.get(`paragraph-${p.id}`) ?? p.text).trim() })) } : m) }));
    setEditing(false); setNotice("演示资料已保存到当前浏览器；此前回答保留为历史，重新提问会使用新资料。");
  }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const title = String(form.get("title") || "").trim(); const body = String(form.get("body") || "").trim();
    const author = String(form.get("author") || "").trim();
    const manuscript: Manuscript = { id: `DEMO-${id().slice(0, 8)}`, short: title, title, stage: "投稿准备", task: "补齐资料并核对", due: dateKey(new Date()), abstract: "摘要待补充。", authors: [{ name: author, affiliation: "", email: "", orcid: "" }], paragraphs: [{ id: "abstract", heading: "摘要", text: "摘要待补充。" }, { id: "body", heading: "录入正文", text: body }] };
    setState(prev => ({ ...prev, manuscripts: [...prev.manuscripts, manuscript], selected: manuscript.id })); setPanel(null); setTab("稿件"); setEditing(false); setNotice("已创建本地演示稿件，尚未投稿或写入业务数据库。");
  }
  async function importText(input: HTMLInputElement) {
    const targetId = selected?.id; const upload = input.files?.[0]; input.value = "";
    if (!upload || !targetId) return;
    if (upload.size > 1024*1024 || !/\.(txt|md)$/i.test(upload.name)) { setNotice("请选择1 MB以内的 UTF-8 TXT 或 Markdown。PDF/DOCX 解析尚未接通。"); return; }
    try {
      const body = new TextDecoder("utf-8", { fatal: true }).decode(await upload.arrayBuffer());
      if (!body.trim()) throw new Error("empty");
      setState(prev => ({ ...prev, manuscripts: prev.manuscripts.map(m => m.id === targetId ? { ...m, paragraphs: [...m.paragraphs.filter(p => p.id !== "imported"), { id: "imported", heading: `导入文本：${upload.name}`, text: body }] } : m) }));
      setNotice("文本已保存到本地演示材料；预设模拟问答仅分析样例内已定义的段落，不声称已审阅导入全文。");
    } catch { setNotice("文件为空或不是有效的 UTF-8 文本，请转换编码后重试。"); }
  }

  function calendar() {
    const start = (month.getDay()+6)%7;
    const count = new Date(month.getFullYear(), month.getMonth()+1, 0).getDate();
    return <section className={s.calendar} aria-label="稿件截止日日历">
      <div className={s.calendarHead}><strong>{month.getFullYear()}年{month.getMonth()+1}月</strong><button aria-label="上个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth()-1, 1))}><Glyph name="back" size={14}/></button><button aria-label="下个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth()+1, 1))}><Glyph name="arrow" size={14}/></button><button onClick={() => { setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1)); setDayFilter(""); }}>今天</button></div>
      <div className={s.dates}>{["一","二","三","四","五","六","日"].map(d => <span key={d}>{d}</span>)}{Array.from({length:start},(_,i) => <span key={`empty-${i}`} />)}{Array.from({length:count}, (_, i) => {
        const key = dateKey(new Date(month.getFullYear(), month.getMonth(), i+1)); const tasks = state.manuscripts.filter(m => m.due === key).length;
        return <button key={key} className={`${key === dateKey(new Date()) ? s.today : ""} ${dayFilter === key ? s.chosenDay : ""}`} aria-label={`${key}${tasks ? `，${tasks}项待办` : "，无待办"}`} aria-pressed={dayFilter === key} onClick={() => setDayFilter(dayFilter === key ? "" : key)}>{i+1}{tasks > 0 && <i />}</button>;
      })}</div>
      {dayFilter && <button className={s.clearFilter} onClick={() => setDayFilter("")}>清除日期筛选 · {dayFilter.slice(5)}</button>}
    </section>;
  }

  function sidebar() {
    const visible = state.manuscripts.filter(m => (!dayFilter || m.due === dayFilter) && `${m.title} ${m.id}`.toLowerCase().includes(search.toLowerCase()));
    return <><div className={s.brand}><span className={s.brandIcon}><Glyph name="layers" size={18}/></span>Publishing OS<button aria-label="演示说明" onClick={() => setPanel("about")}><Glyph name="settings" size={16}/></button></div>
      <div className={s.journal}>开放研究 · 演示期刊</div>
      <nav aria-label="工作导航"><button className={`${s.nav} ${!selected ? s.navActive : ""}`} onClick={() => choose("main")}><Glyph name="spark"/>主对话</button><button className={s.nav} onClick={() => setPanel("new")}><Glyph name="file"/>录入演示稿件</button></nav>
      <label className={s.search}><Glyph name="search" size={15}/><input name="manuscript-search" autoComplete="off" aria-label="搜索演示稿件" placeholder="搜索稿件…" value={search} onChange={e => setSearch(e.target.value)}/></label>
      <div className={s.queueTitle}>我的工作 <span>{visible.length}</span></div>
      <div className={s.queue}>{visible.map(m => <button key={m.id} className={`${s.task} ${state.selected === m.id ? s.activeTask : ""}`} onClick={() => choose(m.id)} aria-current={state.selected === m.id ? "page" : undefined}><span className={s.taskTitle}>{m.short}</span><span className={s.taskAction}>{m.task}</span><span className={s.taskMeta}><span>{m.stage}</span><time dateTime={m.due}>{m.due === dateKey(new Date()) ? "今天" : m.due.slice(5)}</time></span></button>)}{!visible.length && <p className={s.empty}>这一天没有匹配的待办。可清除筛选查看全部稿件。</p>}</div>
      {calendar()}<div className={s.identity}><span className={s.avatar}>编</span><div>演示编辑<span>编辑 · 主编 · 审稿人视角待扩展</span></div><button aria-label="重置演示" onClick={() => setPanel("reset")}><Glyph name="back" size={16}/></button></div>
    </>;
  }

  function metadataForm() {
    if (!selected) return null;
    return <form className={s.editForm} autoComplete="off" onSubmit={saveManuscript}><label>题名<input name="title" defaultValue={selected.title} required maxLength={300}/></label><label>摘要<textarea name="abstract" rows={5} defaultValue={selected.abstract} required maxLength={5000}/></label>{selected.paragraphs.filter(p => p.id !== "abstract").map(p => <label key={p.id}>{p.heading}<textarea name={`paragraph-${p.id}`} rows={5} defaultValue={p.text} required maxLength={1048576}/></label>)}{selected.authors.map((a, i) => <fieldset key={i}><legend>作者 {i+1}</legend><label>姓名<input name={`name-${i}`} defaultValue={a.name} required maxLength={100}/></label><label>机构<input name={`affiliation-${i}`} defaultValue={a.affiliation} maxLength={200}/></label><label>邮箱<input type="email" spellCheck={false} name={`email-${i}`} defaultValue={a.email} maxLength={200}/></label><label>ORCID（手工录入，未经认证）<input name={`orcid-${i}`} spellCheck={false} defaultValue={a.orcid} placeholder="0000-0000-0000-0000" pattern="[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]" maxLength={19}/></label></fieldset>)}<p className={s.small}>仅使用合成或已获授权的公开资料。请勿填写保密稿件或真实私人信息。</p><div className={s.formActions}><button type="button" onClick={() => setEditing(false)}>取消</button><button className={s.primary} type="submit">保存演示资料</button></div></form>;
  }

  function context(prefix = "desktop") {
    return <><div className={s.contextTitle}><Glyph name="file" size={16}/><strong>稿件资料</strong>{selected && <button aria-label="编辑稿件资料" onClick={() => setEditing(!editing)}>{editing ? "返回" : "编辑"}</button>}</div>
      {!selected ? <div className={s.contextEmpty}><Glyph name="file" size={28}/><h2>从一篇稿件开始</h2><p>选择左侧待办，原文、作者信息和引用依据会出现在这里。主对话可以讨论全刊工作。</p><button onClick={() => choose(state.manuscripts[0].id)}>打开第一篇稿件</button></div> : <>
      <div className={s.manuscriptHead}><span>{selected.id} · V1</span><h2>{selected.title}</h2><div className={s.stage}><i/>{selected.stage}<time dateTime={selected.due}>截止 {selected.due.slice(5)}</time></div><details className={s.progress}><summary>查看流程与下一步</summary><ol>{STEPS.map(step => <li key={step} aria-current={selected.stage === step ? "step" : undefined}>{step}</li>)}</ol><p>当前任务：{selected.task}。正式投稿、审稿意见与编辑决定均须负责人另行确认。</p></details></div>
      {editing ? metadataForm() : <><div className={s.tabs} role="tablist" aria-label="稿件资料类型">{(["稿件", "作者", "证据"] as Tab[]).map(t => <button key={t} role="tab" id={`demo-${prefix}-tab-${t}`} aria-selected={tab === t} aria-controls={`demo-${prefix}-panel-${t}`} tabIndex={tab === t ? 0 : -1} onClick={() => {setTab(t); setFocusSource("");}} onKeyDown={e => { const tabs: Tab[] = ["稿件","作者","证据"]; let next = tabs.indexOf(t); if(e.key === "ArrowRight") next = (next+1)%3; else if(e.key === "ArrowLeft") next = (next+2)%3; else if(e.key === "Home") next = 0; else if(e.key === "End") next = 2; else return; e.preventDefault(); setTab(tabs[next]); document.getElementById(`demo-${prefix}-tab-${tabs[next]}`)?.focus(); }}>{t}</button>)}</div>
      <div className={s.materialBody} role="tabpanel" id={`demo-${prefix}-panel-${tab}`} aria-labelledby={`demo-${prefix}-tab-${tab}`} tabIndex={0}>
      {tab === "稿件" && <><div className={s.materialTools}><span>合成演示正文</span><button onClick={() => file.current?.click()}>导入文本</button></div>{selected.paragraphs.map(p => <section key={p.id} data-demo-source={p.id} className={`${s.paragraph} ${focusSource === p.id ? s.highlight : ""}`}><h3>{p.heading}</h3><p>{p.text}</p><button className={s.askParagraph} onClick={() => {setPanel(null); setState(prev => ({...prev, drafts: {...prev.drafts, [thread]: `我想讨论“${p.heading}”：${p.text.slice(0,200)}`}})); composer.current?.focus();}}>围绕此段提问</button></section>)}</>}
      {tab === "作者" && <><p className={s.small}>以下为虚构作者。手工填写 ORCID 不代表身份认证。</p>{selected.authors.map((a, i) => <section key={i} className={s.author}><h3>{a.name}<span>{i+1 === 1 ? "通讯作者 · 示例" : "作者"}</span></h3><dl><dt>机构</dt><dd>{a.affiliation || "待补充"}</dd><dt>邮箱</dt><dd>{a.email || "待补充"}</dd><dt>ORCID</dt><dd>{a.orcid || "未提供"}<span className={s.unverified}>未认证</span></dd></dl></section>)}<div className={s.missing}><h3>待负责人核对</h3><ul><li>作者顺序与贡献声明</li><li>本人 ORCID 授权与机构信息</li><li>伦理、利益冲突与数据可用性声明</li></ul><button onClick={() => setEditing(true)}>补充演示资料</button></div></>}
      {tab === "证据" && <><section className={s.evidence}><h3>稿件内部依据</h3>{selected.paragraphs.map(p => <button key={p.id} onClick={() => source(p.id)}><Glyph name="file" size={15}/>{p.heading}<span>演示版</span></button>)}</section>{hasReference(selected) ? <section data-demo-source="external" className={s.evidence}><h3>公开参考文献</h3><p>{REFERENCE.title}</p><span className={s.small}>{REFERENCE.authors}</span><a href={REFERENCE.url} target="_blank" rel="noopener noreferrer">出版社原文 <Glyph name="arrow" size={14}/></a><a href={REFERENCE.record} target="_blank" rel="noopener noreferrer">Crossref 元数据 <Glyph name="arrow" size={14}/></a><p className={s.small}>DOI {REFERENCE.doi}。Crossref记录已核对，出版社页面可能要求浏览器验证；不证明本稿结论，非实时检索。</p></section> : <p className={s.small}>尚未提供可核对的外部文献，不生成示例链接。</p>}</>}
      </div></>}
      </>}
    </>;
  }

  if (!ready) return <main className={s.loading}>正在打开 Publishing OS 演示…</main>;
  return <div className={s.workspace}>
    <aside className={s.sidebar} aria-label="我的工作与日历">{sidebar()}</aside>
    <a href="#demo-message" className={s.skip}>跳到对话输入框</a>
    <main className={s.conversation}>
      <header className={s.topbar}><button className={s.mobileTasks} aria-label="打开我的工作" onClick={() => setPanel("tasks")}><Glyph name="layers"/></button><span className={s.activeTitle}>{selected ? selected.short : "主对话"}</span><button className={s.demoTag} onClick={() => setPanel("about")}>交互演示</button><button className={s.mobileMaterial} onClick={() => setPanel("material")}><Glyph name="file" size={16}/>资料</button></header>
      <div className={s.transcript} ref={transcript} role="log" aria-label={selected ? `${selected.id}稿件对话` : "主对话记录"} aria-live="polite" aria-relevant="additions">
        <div className={s.threadHeading}><h1>{selected ? "一起读懂这篇稿件" : "从今天的工作开始"}</h1></div>
        {messages.map((m: Message) => <article key={m.id} className={m.role === "user" ? s.userMessage : s.assistantMessage}><div className={s.messageAuthor}>{m.role === "user" ? "你" : <><Glyph name="spark" size={15}/>Publishing OS <span>模拟回答</span></>}</div><div className={s.messageText}>{m.text}</div>{!!m.sources?.length && <div className={s.citations}>{m.sources.map(c => <button key={c} onClick={() => { if(m.evidence?.[c === "external" ? "references" : c] !== selected?.paragraphs.find(p => p.id === (c === "external" ? "references" : c))?.text) {setNotice("这条历史回答引用的资料已修改，不能把当前正文当作原依据。请重新提问。"); return;} source(c); }}><Glyph name={c === "external" ? "search" : "file"} size={13}/>{c === "external" ? "公开文献" : selected?.paragraphs.find(p => p.id === c)?.heading || "原文"}</button>)}</div>}</article>)}
      </div>
      <div className={s.composerWrap}>{notice && <div className={s.notice} role="status"><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice("")}><Glyph name="close" size={14}/></button></div>}{storageError && <p role="alert" className={s.notice}>浏览器无法保存演示资料。请允许本地存储或复制需要保留的文字；刷新可能丢失改动。</p>}
        <div className={s.suggestions}>{(selected ? ["概括这篇稿件","检查方法","核对作者信息","查看参考文献"] : ["今天有哪些工作？","下一步先处理什么？"]).map(q => <button key={q} onClick={() => send(q)}>{q}</button>)}</div>
        <form className={s.composer} onSubmit={e => { e.preventDefault(); send(); }}><label className={s.srOnly} htmlFor="demo-message">对话消息</label><textarea ref={composer} id="demo-message" placeholder={selected ? "围绕这篇稿件，问任何问题…" : "询问全刊工作，或从一篇稿件开始…"} value={draft} maxLength={3000} rows={2} onChange={e => setState(prev => ({...prev, drafts: {...prev.drafts, [thread]: e.target.value}}))} onKeyDown={e => {if(e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); send();}}}/><div className={s.composerBottom}><span><Glyph name="file" size={14}/>{selected ? "当前稿件 · V1" : "全刊工作"}</span><button type="submit" className={s.send} disabled={!draft.trim()} aria-label="发送消息"><Glyph name="arrow" size={18}/></button></div></form><div className={s.footnote}>模拟对话 · 合成稿件 · 仅保存在当前浏览器</div>
      </div>
    </main>
    <aside className={s.context} aria-label="当前稿件资料">{context()}</aside>
    <input type="file" accept=".txt,.md" ref={file} className={s.hidden} aria-label="导入演示文本" onChange={e => {void importText(e.currentTarget);}}/>
    {panel && <Sheet title={panel === "tasks" ? "我的工作" : panel === "material" ? "稿件资料" : panel === "about" ? "关于产品演示" : panel === "reset" ? "重置演示" : "录入演示稿件"} close={() => setPanel(null)}>
      {panel === "tasks" && <div className={s.drawerSide}>{sidebar()}</div>}{panel === "material" && <div className={s.drawerContext}>{context("drawer")}</div>}
      {panel === "about" && <div className={s.sheetBody}><h2>让对话围绕真实材料展开</h2><p>左侧找到需要处理的工作，中间持续讨论，右侧核对稿件、作者和来源。AI辅助整理，负责人保留判断与确认权。</p><p>当前是独立的产品交互演示：原创合成稿件、预设模拟回答、浏览器本地存储。未连接模型、业务数据库、邮箱或 ORCID 认证。</p><p>参考文献指向公开出版社与 Crossref；不会据此宣称已核验稿件结论。请勿录入保密稿件、凭据或真实私人资料。</p><p>这台设备上的资料可以通过“重置演示”清除。</p><button onClick={() => setPanel(null)} className={s.primary}>开始体验</button></div>}
      {panel === "reset" && <div className={s.sheetBody}><p>清除当前浏览器内的演示对话、资料修改和新增稿件，恢复初始合成样例。不会影响真实业务数据库。</p><div className={s.formActions}><button onClick={() => setPanel(null)}>取消</button><button className={s.primary} onClick={() => { setState(initialState()); setPanel(null); setEditing(false); setDayFilter(""); setSearch(""); setTab("稿件"); setNotice("已恢复初始演示资料。"); }}>确认重置</button></div></div>}
      {panel === "new" && <form className={s.editForm} onSubmit={create}><p className={s.small}>仅录入合成或公开授权文本，保存到当前浏览器，不构成正式投稿。</p><label>稿件题名<input required name="title" maxLength={300}/></label><label>示例作者姓名<input required name="author" maxLength={100}/></label><label>稿件正文<textarea required name="body" rows={8} maxLength={20000} placeholder="把演示材料放在这里，再从资料面板补充元数据。"/></label><button className={s.primary} type="submit">创建本地演示稿件</button></form>}
    </Sheet>}
  </div>;
}
