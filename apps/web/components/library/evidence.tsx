"use client";

import { useEffect, useRef } from "react";
import type { Citation, Dossier, ExternalReference, Message } from "./types";
import styles from "./library.module.css";
import { fileDownloadURL } from "./api";
import { documentLocation } from "./document-details";

const format = new Intl.NumberFormat("zh-CN");

function fieldText(data: Dossier["data"], path: string | null): string | null {
  if (!path || !/^(?:title|abstract|language|source_kind|source_note|keywords\.\d+|authors\.\d+\.(?:name|email|orcid|corresponding|source_note|affiliations\.\d+|contributions\.\d+))$/.test(path)) return null;
  let value: unknown = data;
  for (const part of path.split(".")) {
    if (!value || typeof value !== "object" || !Object.hasOwn(value, part)) return null;
    value = (value as Record<string, unknown>)[part];
  }
  return typeof value === "string" || typeof value === "boolean" ? String(value) : null;
}

export function citationText(snapshot: Dossier, citation: Citation): string | null {
  if (snapshot.version_id !== citation.version_id || snapshot.content_digest !== citation.content_digest || snapshot.version_no !== citation.version_no) return null;
  if (citation.kind === "text" && (!snapshot.file || snapshot.file.sha256 !== citation.file_sha256)) return null;
  if (citation.document) {
    const document = snapshot.document;
    const original = citation.document;
    if (!document || !snapshot.file || document.origin_digest !== original.origin_digest || document.sha256 !== original.sha256 || document.filename !== original.filename || document.media_type !== original.media_type) return null;
    const start = citation.kind === "text" ? citation.start : original.source_start;
    const end = citation.kind === "text" ? citation.end : original.source_end;
    const quote = citation.kind === "text" ? citation.quote : original.source_quote;
    if (start == null || end == null || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end <= start || !quote || Array.from(snapshot.file.text).slice(start, end).join("") !== quote) return null;
    const locations = document.segments.filter(segment => segment.start < end && segment.end > start).map(segment => ({ kind: segment.kind, number: segment.number, start: Math.max(start, segment.start), end: Math.min(end, segment.end) }));
    if (!locations.length || locations.length !== original.locations.length || locations.some((location, index) => Object.entries(location).some(([key, value]) => original.locations[index][key as keyof typeof location] !== value))) return null;
  }
  const text = citation.kind === "text" ? snapshot.file?.text : fieldText(snapshot.data, citation.field_path);
  if (text == null || !citation.quote || !citation.source_text.includes(citation.quote)) return null;
  if (!Number.isSafeInteger(citation.start) || !Number.isSafeInteger(citation.end) || citation.start < 0 || citation.end <= citation.start) return null;
  const characters = Array.from(text);
  return characters.slice(citation.start, citation.end).join("") === citation.quote ? text : null;
}

function referenceLinks(reference: ExternalReference) {
  if (reference.status !== "verified_metadata" || reference.scope !== "bibliographic_metadata_only" || reference.doi.length > 256 || !/^10\.\d{4,9}\/[^\s<>]+$/u.test(reference.doi)) return null;
  // Never render a model-supplied or remote record's arbitrary URL.
  const path = encodeURIComponent(reference.doi).replaceAll("%2F", "/");
  return { doi: `https://doi.org/${path}`, source: `https://api.crossref.org/works/${path}` };
}

export function MessageTurn({ message, currentVersionId, locating, onCitation }: { message: Message; currentVersionId: string; locating: string | null; onCitation: (citation: Citation, trigger: HTMLButtonElement) => void }) {
  const coverage = message.coverage;
  const grounded = message.provider !== "rules" && Array.isArray(message.claims) && message.claims.length > 0;
  const references = (message.external_references ?? []).flatMap(reference => { const links = referenceLinks(reference); return links ? [{ reference, links }] : []; });
  return <article className={styles.turn}>
    <p className={styles.userQuestion}>{message.question}</p>
    <small>v{message.version_no}{message.version_id !== currentVersionId ? " · 历史版本" : ""} · {message.provider === "rules" ? "规则引导 · 未调用模型" : message.provider === "mock" ? "Mock · 模拟结果" : "DeepSeek"}</small>
    {grounded ? <div className={styles.claims}>{message.claims!.map((claim, index) => <div className={styles.claim} key={index}>
      <p className={styles.answer}>{claim.text}</p>
      <div className={styles.citations}>{claim.citations.map((citation, position) => <button type="button" key={`${citation.source_id}:${position}`} onClick={event => onCitation(citation, event.currentTarget)} aria-label={`定位原文：${citation.label}，v${citation.version_no}`} aria-busy={locating === `${citation.version_id}:${citation.source_id}`}>
        {citation.label} · v{citation.version_no}{locating === `${citation.version_id}:${citation.source_id}` ? " · 定位中…" : ""}
      </button>)}</div>
    </div>)}</div> : <div className={styles.answer}>{message.answer}</div>}
    {grounded && !!message.questions?.length && <section className={styles.references} aria-label="待确认问题"><h3>待确认</h3><ul>{message.questions.map((question, index) => <li key={index}>{question}</li>)}</ul></section>}
    {coverage ? <p className={styles.coverage}>本轮读取 {format.format(coverage.read_chunks)} / {format.format(coverage.total_chunks)} 个资料片段 · {format.format(coverage.read_characters)} / {format.format(coverage.total_characters)} 字符{coverage.fulltext_available === false ? " · 未上传全文，仅元数据" : coverage.complete ? " · 覆盖全部资料片段" : " · 部分覆盖，不能据此排除其他内容"}</p> : message.provider !== "rules" && <p className={styles.coverage}>本轮读取范围未提供。</p>}
    {references.length > 0 && <section className={styles.references} aria-label="外部文献来源"><h3>外部文献</h3><p className={styles.hint}>Crossref 元数据匹配；未读取文献全文，不代表科学结论已证实。</p>{references.map(({ reference, links }) => <div className={styles.reference} key={reference.doi}>
      <a href={links.doi} target="_blank" rel="noopener noreferrer">{reference.title || reference.doi}</a>
      <p>{reference.authors.join("、")}{reference.year ? ` · ${reference.year}` : ""}</p>
      <div><a href={links.source} target="_blank" rel="noopener noreferrer">Crossref 记录</a><span>DOI: {reference.doi}</span></div>
    </div>)}</section>}
  </article>;
}

export function EvidencePanel({ snapshot, citation, currentVersionId, onClose }: { snapshot: Dossier; citation: Citation; currentVersionId: string; onClose: () => void }) {
  const highlight = useRef<HTMLElement>(null);
  const text = citationText(snapshot, citation);
  useEffect(() => {
    if (text === null) return;
    highlight.current?.focus({ preventScroll: true });
    highlight.current?.scrollIntoView({ block: "center" });
  }, [text, citation]);
  const characters = text === null ? [] : Array.from(text);
  const originalURL = citation.document && snapshot.document ? fileDownloadURL(snapshot.document.download_url) : null;
  return <div className={styles.evidencePanel}>
    <div className={styles.materialHeader}><h2>{citation.kind === "text" ? "原文定位" : "作者与资料定位"} · v{citation.version_no}</h2><button type="button" onClick={onClose}>返回当前资料</button></div>
    <div className={styles.evidenceBody}>
      <p className={styles.hint}>{snapshot.version_id !== currentVersionId || !snapshot.is_current ? "历史版本的证据；当前资料与未保存编辑保持不变。" : "当前已保存版本的证据。"}</p>
      <h3>{citation.label}</h3>
      {citation.document ? <div className={styles.documentOrigin}><p className={styles.hint}>{citation.document.filename} · {citation.document.locations.map(location => documentLocation(location.kind, location.number)).join("、")}</p>{originalURL && text !== null && <a href={originalURL} download>下载原稿</a>}{citation.kind === "metadata" && text !== null && <blockquote>{citation.document.source_quote}</blockquote>}</div> : citation.kind === "text" && <p className={styles.hint}>{snapshot.file?.filename}{citation.line_start != null ? ` · 第 ${citation.line_start}${citation.line_end !== citation.line_start && citation.line_end != null ? `–${citation.line_end}` : ""} 行` : ""}</p>}
      {citation.kind === "metadata" && <p className={styles.hint}>录入资料，不代表作者或 ORCID 身份已认证</p>}
      {text === null ? <p role="alert">引用与版本内容不匹配，请重新载入资料后再定位。</p> : <pre className={styles.locatedText}>{characters.slice(0, citation.start).join("")}<mark ref={highlight} tabIndex={-1} aria-label="已定位引用原文">{characters.slice(citation.start, citation.end).join("")}</mark>{characters.slice(citation.end).join("")}</pre>}
      <details><summary>证据版本 SHA-256</summary><code>{citation.content_digest}</code>{citation.file_sha256 && <><p className={styles.hint}>原文文件 SHA-256</p><code>{citation.file_sha256}</code></>}</details>
    </div>
  </div>;
}
