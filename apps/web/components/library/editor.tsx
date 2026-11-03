"use client";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import type { Author, Dossier, DossierData, Upload } from "./types";
import styles from "./library.module.css";

const emptyAuthor = (): Author => ({ name: "", email: "", orcid: null, affiliations: [], corresponding: false, contributions: [], source_note: "" });
export default function DossierEditor({ detail, hidden, busy, saving, onDirty, onSave, importReview }: { detail: Dossier; hidden: boolean; busy: boolean; saving: boolean; onDirty: (value: boolean) => void; onSave: (data: DossierData, file: Upload | null) => Promise<void>; importReview?: { confirmation: ReactNode; canSubmit: boolean } }) {
  const [data, setData] = useState<DossierData>(() => structuredClone(detail.data));
  const [keywords, setKeywords] = useState(detail.data.keywords.join(", "));
  const [file, setFile] = useState<Upload | null>(null);
  const [fileError, setFileError] = useState("");
  const [reading, setReading] = useState(false);
  const fileGeneration = useRef(0);
  const [validationError, setValidationError] = useState("");
  const [changed, setChanged] = useState(false);
  function markDirty() { setChanged(true); onDirty(true); }
  function update<K extends keyof DossierData>(key: K, value: DossierData[K]) { setData(previous => ({ ...previous, [key]: value })); markDirty(); }
  function author(index: number, patch: Partial<Author>) { update("authors", data.authors.map((value, position) => position === index ? { ...value, ...patch } : value)); }
  function move(index: number, direction: -1 | 1) { const authors = [...data.authors]; [authors[index], authors[index + direction]] = [authors[index + direction], authors[index]]; update("authors", authors); }
  async function readFile(value: File | undefined) {
    const current = ++fileGeneration.current;
    setFile(null); setFileError(""); setReading(false);
    if (!value) return;
    if (!/\.(txt|md)$/i.test(value.name) || value.size > 1024 * 1024 || !value.size) { setFileError("请选择非空的 UTF-8 TXT 或 Markdown 文件，最大 1 MiB。"); return; }
    setReading(true);
    try {
      const bytes = new Uint8Array(await value.arrayBuffer());
      new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      if (current !== fileGeneration.current) return;
      setFile({ filename: value.name, content_base64: btoa(binary) }); markDirty();
    } catch { if (current === fileGeneration.current) setFileError("无法读取 UTF-8 文本，请检查文件编码后重新选择。"); }
    finally { if (current === fileGeneration.current) setReading(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const keywordList = keywords.split(/[,，;；\n]/).map(value => value.trim()).filter(Boolean);
    const invalid = keywordList.length > 12 || keywordList.some(value => value.length > 80) ? "关键词最多 12 项，每项最多 80 字。" : data.authors.some(value => value.affiliations.length > 20 || value.affiliations.some(item => item.length > 500)) ? "每位作者最多 20 项机构，每项最多 500 字。" : "";
    const contributionError = data.authors.some(value => (value.contributions ?? []).length > 20 || (value.contributions ?? []).some(item => item.length > 100)) ? "每位作者最多 20 项贡献，每项最多 100 字。" : "";
    const completenessError = importReview && (!data.authors.length || data.authors.filter(value => value.corresponding).length !== 1 || !keywordList.length) ? "请补充至少 1 个关键词和 1 位作者，并选择唯一通讯作者。" : "";
    setValidationError(invalid || contributionError || completenessError);
    if (invalid || contributionError || completenessError || (importReview && !importReview.canSubmit)) return;
    void onSave({ ...data, keywords: keywordList, authors: data.authors.map(value => ({ ...value, orcid: value.orcid?.trim() || null, contributions: (value.contributions ?? []).map(item => item.trim()).filter(Boolean), affiliations: value.affiliations.map(item => item.trim()).filter(Boolean) })) }, file);
  }
  return <form hidden={hidden} className={styles.form} onSubmit={submit}>
    <fieldset disabled={busy || reading}>
      <label>题名<input name="title" required={!!importReview} minLength={importReview ? 3 : undefined} autoComplete="off" value={data.title} maxLength={500} onChange={event => update("title", event.target.value)} /></label>
      <label>摘要<textarea name="abstract" required={!!importReview} minLength={importReview ? 40 : undefined} value={data.abstract} maxLength={12000} rows={7} onChange={event => update("abstract", event.target.value)} /></label>
      <div className={styles.fieldPair}><label>语言<select name="language" value={data.language} onChange={event => update("language", event.target.value as "zh" | "en")}><option value="zh">中文</option><option value="en">English</option></select></label><label>关键词<input name="keywords" required={!!importReview} autoComplete="off" value={keywords} maxLength={2000} onChange={event => { setKeywords(event.target.value); markDirty(); }} placeholder="用逗号分隔…" /></label></div>
      <section className={styles.authors}><div className={styles.sectionHeading}><h2>作者与机构</h2><button type="button" disabled={data.authors.length >= 20} onClick={() => update("authors", [...data.authors, emptyAuthor()])}>添加作者</button></div>
        {!data.authors.length && <p className={styles.hint}>尚无作者。作者身份由录入资料提供，不代表本人认证。</p>}
        {data.authors.map((value, index) => <fieldset className={styles.author} key={index}><legend>作者 {index + 1}</legend><div className={styles.fieldPair}><label>姓名<input name={`author-${index}-name`} required={!!importReview} autoComplete="off" value={value.name} maxLength={200} onChange={event => author(index, { name: event.target.value })} /></label><label>邮箱<input name={`author-${index}-email`} required={!!importReview && value.corresponding} type="email" spellCheck={false} autoComplete="off" value={value.email} maxLength={254} onChange={event => author(index, { email: event.target.value })} /></label></div><label>机构（每行一项）<textarea name={`author-${index}-affiliations`} required={!!importReview} rows={3} value={value.affiliations.join("\n")} maxLength={4000} onChange={event => author(index, { affiliations: event.target.value.split("\n") })} /></label><label>作者贡献（选填，每行一项）<textarea name={`author-${index}-contributions`} rows={3} value={(value.contributions ?? []).join("\n")} maxLength={2019} onChange={event => author(index, { contributions: event.target.value.split("\n") })} /></label><label>ORCID（选填，未认证）<input name={`author-${index}-orcid`} spellCheck={false} autoComplete="off" value={value.orcid || ""} maxLength={64} onChange={event => author(index, { orcid: event.target.value || null })} placeholder="0000-0000-0000-0000…" /></label><label>作者 / ORCID 来源<textarea name={`author-${index}-source`} required={!!importReview} rows={2} value={value.source_note} maxLength={1000} onChange={event => author(index, { source_note: event.target.value })} /></label><label className={styles.checkbox}><input type="radio" name="corresponding-author" checked={value.corresponding} onChange={() => update("authors", data.authors.map((item, position) => ({ ...item, corresponding: position === index })))} /><span>通讯作者</span></label><div className={styles.authorActions}><button type="button" disabled={index === 0} aria-label={`上移作者 ${index + 1}`} onClick={() => move(index, -1)}>上移</button><button type="button" disabled={index === data.authors.length - 1} aria-label={`下移作者 ${index + 1}`} onClick={() => move(index, 1)}>下移</button><button type="button" aria-label={`删除作者 ${index + 1}`} onClick={() => { if ((!value.name && !value.email && !value.affiliations.length && !value.orcid && !value.source_note) || window.confirm(`删除作者 ${index + 1}${value.name ? `：${value.name}` : ""}？保存新版本后生效。`)) update("authors", data.authors.filter((_, position) => position !== index)); }}>删除作者</button></div></fieldset>)}
      </section>
      <label>资料类型<select name="source-kind" value={data.source_kind} onChange={event => update("source_kind", event.target.value as DossierData["source_kind"])}><option value="synthetic">合成资料</option><option value="public_authorized">公开 / 已获授权资料</option></select></label>
      <label>来源与授权说明<textarea name="source-note" rows={3} required minLength={5} maxLength={2000} value={data.source_note} onChange={event => update("source_note", event.target.value)} /></label>
      {!importReview && <><label>原文文件<input name="file" type="file" accept=".txt,.md,text/plain,text/markdown" aria-describedby="library-file-help library-file-error" onChange={event => void readFile(event.target.files?.[0])} /></label>
      <p id="library-file-help" className={styles.hint}>{reading ? "正在读取文件…" : file ? `待保存：${file.filename}` : detail.file ? `当前：${detail.file.filename}；未选择新文件时沿用本版原文。` : "UTF-8 TXT / Markdown，最大 1 MiB。"}</p>
      {fileError && <p id="library-file-error" className={styles.fieldError} role="alert">{fileError}</p>}
      {file && <button type="button" onClick={() => { ++fileGeneration.current; setFile(null); markDirty(); }}>取消更换文件</button>}</>}
    </fieldset>
    {!importReview && detail.missing.length > 0 && <section className={styles.missing}><h2>当前已保存版本的缺项</h2><ul>{detail.missing.map((item, index) => <li key={`${item.field}-${index}`}>{item.message}</li>)}</ul></section>}
    {validationError && <p className={styles.fieldError} role="alert">{validationError}</p>}
    {importReview?.confirmation}
    <button className={styles.primary} type="submit" disabled={(!changed && !importReview) || busy || reading || !!fileError || !!(importReview && !importReview.canSubmit)}>{saving ? "保存中…" : importReview ? "核对并保存为新版本" : "保存为新版本"}</button>
  </form>;
}
