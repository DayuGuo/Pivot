"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import DossierEditor from "./editor";
import { documentLocation, documentWarning } from "./document-details";
import { fieldLabel } from "./import-labels";
import { uncertaintyText } from "./uncertainty";
import { fileDownloadURL } from "./api";
import type { DocumentImport, Dossier, DossierData } from "./types";
import styles from "./library.module.css";

type FieldSource = DocumentImport["field_sources"][number];
const tabs = [["fields", "核对表单"], ["text", "提取全文"], ["sources", "识别依据"]] as const;


export default function ImportReview({ imported, detail, busy, onDirty, onConfirm }: {
  imported: DocumentImport; detail: Dossier; busy: boolean; onDirty: (value: boolean) => void; onConfirm: (data: DossierData, materialOnly: boolean) => Promise<void>;
}) {
  const [tab, setTab] = useState<(typeof tabs)[number][0]>("fields");
  const [acknowledged, setAcknowledged] = useState(false);
  const [materialOnly, setMaterialOnly] = useState(false);
  const hasSavedFields = !!detail.file || detail.version_no > 1 || !!(detail.data.title.trim() || detail.data.abstract.trim() || detail.data.authors.length || detail.data.keywords.length);
  const [useSaved, setUseSaved] = useState(hasSavedFields);
  const [formEdits, setFormEdits] = useState(false);
  const [formGeneration, setFormGeneration] = useState(0);
  const [source, setSource] = useState<FieldSource | null>(null);
  const [sourceError, setSourceError] = useState("");
  const mark = useRef<HTMLElement>(null);
  const original = fileDownloadURL(imported.original_download_url);
  const confirmed = imported.confirmed_version_id;
  const editable = imported.editable && !confirmed && detail.revision === imported.base_revision && detail.version_id === imported.base_version_id;
  const preservedData: DossierData = {
    ...imported.proposed_data,
    title: detail.data.title.trim() ? detail.data.title : imported.proposed_data.title,
    abstract: detail.data.abstract.trim() ? detail.data.abstract : imported.proposed_data.abstract,
    keywords: detail.data.keywords.length ? detail.data.keywords : imported.proposed_data.keywords,
    authors: detail.data.authors.length ? detail.data.authors : imported.proposed_data.authors,
    language: detail.version_no > 1 ? detail.data.language : imported.proposed_data.language,
    source_kind: detail.data.source_kind, source_note: detail.data.source_note,
  };
  const candidate: Dossier = { ...detail, data: useSaved && !confirmed ? preservedData : imported.proposed_data, missing: [] };
  const characters = Array.from(imported.text);
  useEffect(() => {
    if (tab !== "text" || !source) return;
    mark.current?.focus({ preventScroll: true }); mark.current?.scrollIntoView({ block: "center" });
  }, [tab, source]);
  function locate(value: FieldSource) {
    const valid = Number.isSafeInteger(value.start) && Number.isSafeInteger(value.end) && value.start >= 0 && value.end > value.start && characters.slice(value.start, value.end).join("") === value.quote && imported.segments.some(segment => segment.kind === value.kind && segment.number === value.number && value.start >= segment.start && value.start < segment.end);
    if (!valid) { setSource(null); setSourceError("识别依据与提取文本不匹配，请下载原件人工检查。"); return; }
    setSourceError(""); setSource({ ...value }); setTab("text");
  }
  return <><div className={styles.materialHeader}><h2>导入核对</h2><Link href={`/library?dossier=${detail.id}`}>返回当前资料</Link></div>
    <div className={styles.importOverview}>
      <strong>{imported.filename}</strong>{original && <a href={original} download>下载原稿</a>}
      <p className={styles.hint}>{imported.metadata_provider === "deepseek" ? "DeepSeek 提取候选" : "Mock / 规则提取候选，未调用模型"}{confirmed ? " · 已核对保存为新版本" : ` · 待人工核对，当前仍为 v${detail.version_no}`}</p>
      {confirmed ? <p className={styles.notice}>本导入已核对保存。以下保留原始识别候选，<Link href={`/library/review/${confirmed}?dossier=${detail.id}`}>查看保存后的版本</Link>。</p> : !editable && <p className={styles.warning}>当前资料已更新，本候选只读。请从当前版本重新导入；不要将旧候选直接覆盖新资料。</p>}
      {!!imported.warnings.length && <ul className={styles.warning}>{imported.warnings.map((warning, index) => <li key={index}>{documentWarning(warning)}</li>)}</ul>}
    </div>
    <div className={styles.importTabs} role="tablist" aria-label="导入核对视图">{tabs.map(([id, label], index) => <button type="button" key={id} id={`import-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`import-panel-${id}`} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} onKeyDown={event => { if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return; event.preventDefault(); const next = tabs[(index + (event.key === "ArrowRight" ? 1 : 2)) % tabs.length][0]; setTab(next); document.getElementById(`import-tab-${next}`)?.focus(); }}>{label}</button>)}</div>
    {sourceError && <p className={styles.sourceError} role="alert">{sourceError}</p>}
    <div className={styles.materialBody}>
      <div id="import-panel-fields" role="tabpanel" aria-labelledby="import-tab-fields" hidden={tab !== "fields"}>
        {editable && hasSavedFields && <section className={`${styles.importOverview} ${styles.candidateComparison}`}>
          <p>{useSaved ? "已有资料字段已保留，空项采用识别候选。替换已有内容前请核对差异。" : "正在使用本次识别候选，保存前请核对与原资料的差异。"}</p>
          <button type="button" disabled={busy} onClick={() => {
            if (formEdits && !window.confirm("切换资料来源会放弃表单中尚未保存的修改。继续？")) return;
            setUseSaved(!useSaved); setFormGeneration(value => value + 1); setFormEdits(false); setAcknowledged(false); onDirty(true);
          }}>{useSaved ? "使用本次识别结果" : "保留当前资料字段"}</button>
          <details><summary>比较已保存字段与识别候选</summary><h3>已保存字段</h3><pre>{JSON.stringify(detail.data, null, 2)}</pre><h3>识别候选</h3><pre>{JSON.stringify(imported.proposed_data, null, 2)}</pre></details>
        </section>}
        {editable && <label className={`${styles.checkbox} ${styles.materialOption}`}><input name="import-material-only" type="checkbox" checked={materialOnly} disabled={busy} onChange={event => { setMaterialOnly(event.target.checked); setAcknowledged(false); onDirty(true); }} /><span>先保存材料，作者及其他缺项稍后补齐</span></label>}
        <DossierEditor key={`${imported.id}:${formGeneration}`} detail={candidate} hidden={false} importIssues={imported.metadata_uncertainties} busy={busy || !editable} saving={busy} onDirty={value => { setAcknowledged(false); setFormEdits(value); onDirty(value); }} onSave={async data => { if (!editable || !acknowledged) return; setAcknowledged(false); await onConfirm(data, materialOnly); }} importReview={{ materialOnly, canSubmit: editable && acknowledged, confirmation: <section className={styles.confirm}><label className={styles.checkbox}><input name="import-acknowledged" type="checkbox" checked={acknowledged} disabled={!editable || busy} onChange={event => setAcknowledged(event.target.checked)} /><span>{materialOnly ? "我已对照原件核对提取文字和当前表单，确认保存材料；缺项保留待补，不代表完整资料已核对。" : "我已对照原文件逐项核对提取全文和全部作者元数据，确认核对并保存为新版本。"}</span></label><p className={styles.hint}>修改字段后需要重新勾选。本次只确认导入，不提交稿件、认证作者身份或作编辑决定。</p></section> }} />
      </div>
      <section id="import-panel-text" role="tabpanel" aria-labelledby="import-tab-text" hidden={tab !== "text"} className={styles.original}>
        <div className={styles.originalHeading}><h2>提取全文</h2>{source && <span>{documentLocation(source.kind, source.number)}</span>}</div>
        <p className={styles.hint}>请对照原稿核对阅读顺序、表格与特殊符号。页码或段落表示原文件位置，不表示版面完全重建。若全文有误，请修正原文件后重新导入。</p>
        <pre>{source ? <>{characters.slice(0, source.start).join("")}<mark ref={mark} tabIndex={-1} aria-label="已定位提取依据">{characters.slice(source.start, source.end).join("")}</mark>{characters.slice(source.end).join("")}</> : imported.text}</pre>
        <details><summary>原件与解析信息</summary><dl className={styles.facts}><dt>原件 SHA-256</dt><dd><code>{imported.sha256}</code></dd><dt>解析器</dt><dd>{imported.parser}</dd><dt>导入摘要</dt><dd><code>{imported.digest}</code></dd></dl></details>
      </section>
      <section id="import-panel-sources" role="tabpanel" aria-labelledby="import-tab-sources" hidden={tab !== "sources"} className={styles.original}>
        {!!imported.metadata_uncertainties?.length && <section><h2>需要核对的关联</h2>{imported.metadata_uncertainties.map((issue, index) => <div key={`${issue.field_path}:${index}`} className={styles.importSource}><strong>{fieldLabel(issue.field_path)}</strong><p>{uncertaintyText(issue.reason)}</p>{issue.evidence && <button type="button" onClick={() => locate({ ...issue.evidence!, field_path: issue.field_path, value: "" })}>查看原文线索</button>}</div>)}</section>}
        <h2>原始识别依据</h2><p className={styles.hint}>以下为候选识别时的原文。你修改的字段由本人确认，不自动沿用原文来源或作者身份认证。</p>
        {imported.field_sources.length ? imported.field_sources.map((value, index) => <div className={styles.importSource} key={`${value.field_path}:${index}`}><button type="button" onClick={() => locate(value)}>{fieldLabel(value.field_path)} · {documentLocation(value.kind, value.number)}</button><blockquote>{value.quote}</blockquote>{value.association?.evidence.map((span, i) => <button key={i} type="button" onClick={() => locate({ ...span, field_path: value.field_path, value: value.value })}>{fieldLabel(value.field_path)} · 关联依据 {i + 1}</button>)}</div>) : <p>未找到可定位的元数据候选。请根据原稿手动补齐表单。</p>}
      </section>
    </div></>;
}
