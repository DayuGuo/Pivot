"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { LocalPreviewDTO } from "./types";
import { dateText } from "./types";
import { ProofFileView } from "./production";
import { APIError, usePublishing } from "./workspace";
import styles from "./publishing.module.css";

export default function LocalPreview({ previewId }: { previewId: string }) {
  const { setReviewContext } = usePublishing();
  const [preview, setPreview] = useState<LocalPreviewDTO | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/publishing/previews/${encodeURIComponent(previewId)}`, { credentials: "same-origin", cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new APIError(response.status, typeof body.detail === "string" ? body.detail : "本地预览不存在或当前账号无权读取，请返回稿件检查授权。");
      setPreview(body); setError("");
    } catch (failure) { setPreview(null); setError((failure as Error).message); }
    finally { setBusy(false); }
  }, [previewId]);
  // Retrieve an authenticated immutable preview, never static public content.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, [load]);
  // The service DTO is the authority for manuscript context, not the URL query.
  useEffect(() => { setReviewContext(preview?.manuscript_id ?? null); return () => setReviewContext(null); }, [preview?.manuscript_id, setReviewContext]);
  if (!preview) return <section className={styles.panel}><h1>本地预览</h1>{error ? <div className={styles.error} role="alert">{error}<button disabled={busy} onClick={() => { setBusy(true); void load(); }}>重新载入</button><Link href="/publishing">返回出版工作区</Link></div> : <p role="status">正在载入鉴权本地预览…</p>}</section>;
  return <section className={styles.panel} aria-label="鉴权本地预览"><header className={styles.panelHeader}><h1>本地预览</h1><Link href={`/publishing?manuscript=${preview.manuscript_id}`}>返回稿件</Link></header><p className={styles.notice}>尚未正式发表 · 仅向获授权用户展示</p>{error && <p role="alert" className={styles.error}>{error}</p>}
    <article aria-label="本地预览文章"><h1>{preview.metadata_snapshot.title}</h1><p>{preview.metadata_snapshot.authors.map(author => author.name + (author.corresponding ? "（通讯作者）" : "")).join("、")}</p>{preview.metadata_snapshot.authors.map((author, index) => <p className={styles.subtle} key={index}>{author.name}：{author.affiliations.join("；") || "未提供单位"}{author.orcid ? ` · ORCID ${author.orcid}` : ""}</p>)}<h2>摘要</h2><p className={styles.preserve}>{preview.metadata_snapshot.abstract}</p><p className={styles.subtle}>关键词：{preview.metadata_snapshot.keywords.join("、")}</p><p className={styles.subtle}>{preview.metadata_snapshot.language === "zh" ? "中文" : "英文"} · 研究论文</p><section className={styles.section}><h2>正文校样</h2><div className={styles.messageText} data-testid="local-preview-body">{preview.text}</div></section>{preview.metadata_snapshot.funding_statement && <section className={styles.section}><h2>基金资助</h2><p className={styles.preserve}>{preview.metadata_snapshot.funding_statement}</p></section>}<details className={styles.section}><summary>作者贡献</summary>{preview.metadata_snapshot.authors.map((author, index) => <p key={index}>{author.name}：{author.contributions.join("；") || "未提供"}</p>)}</details></article>
    <details className={styles.section}><summary>本地预览来源与内容指纹</summary><p className={styles.subtle}>作者校样通过于 {dateText(preview.proof_approved_at)} · 预览生成于 {dateText(preview.created_at)}</p><ProofFileView file={preview.file} /><p className={styles.hash}>预览 SHA-256：<code>{preview.content_digest}</code></p><p className={styles.subtle}>录用元数据、校样文件和作者回应均固定绑定，不从最新上传文件动态替换。</p></details>
  </section>;
}
