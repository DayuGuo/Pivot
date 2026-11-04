"use client";
import { uncertaintyText } from "./uncertainty";
import { fieldLabel } from "./import-labels";
import { LibraryError } from "./api";
import { useState } from "react";
import Link from "next/link";
import { OriginalText, VersionList } from "./viewers";
import type { Dossier } from "./types";
import styles from "./library.module.css";

export default function DossierReview({ detail, busy, confirming, onConfirm, onUnavailable }: { detail: Dossier; busy: boolean; confirming: boolean; onConfirm: () => Promise<void>; onUnavailable: (error: LibraryError) => void }) {
  const [acknowledged, setAcknowledged] = useState(false);
  const allowed = detail.is_current && !detail.verified && detail.missing.length === 0;
  return <><div className={styles.materialHeader}><h2>核对 v{detail.version_no}</h2><Link href={`/library?dossier=${detail.id}`}>返回资料</Link></div><div className={styles.review}>
    {!detail.is_current && <p className={styles.warning}>这是历史版本，只可查看。请返回资料核对当前版本。</p>}
    {detail.verified && <p className={styles.notice}>此版本已核对{detail.verification ? ` · ${detail.verification.by} · ${new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(detail.verification.at))}` : ""}</p>}
    {!!detail.author_issues?.length && <ul className={styles.warning} aria-label="作者关联提示">{detail.author_issues.map((issue, i) => <li key={i}>{fieldLabel(issue.field_path)}：{uncertaintyText(issue.reason)}</li>)}</ul>}
    <h2>{detail.data.title || "未填写题名"}</h2><dl className={styles.facts}><dt>语言</dt><dd>{detail.data.language === "zh" ? "中文" : "English"}</dd><dt>关键词</dt><dd>{detail.data.keywords.join("、") || "未填写"}</dd><dt>摘要</dt><dd className={styles.multiline}>{detail.data.abstract || "未填写"}</dd><dt>资料类型</dt><dd>{detail.data.source_kind === "synthetic" ? "合成资料" : "公开 / 已获授权资料"}</dd><dt>来源与授权</dt><dd className={styles.multiline}>{detail.data.source_note || "未填写"}</dd></dl>
    <section><h2>作者与机构</h2>{!detail.data.authors.length && <p>未填写作者。</p>}{detail.data.authors.map((author, index) => <article className={styles.reviewAuthor} key={index}><h3>{index + 1}. {author.name || "未填写姓名"}{author.corresponding ? "（通讯作者）" : ""}</h3><dl className={styles.facts}><dt>邮箱</dt><dd>{author.email || "未填写"}</dd><dt>机构</dt><dd>{author.affiliations.length ? author.affiliations.map((item, position) => <div key={position}>{item}</div>) : "未填写"}</dd><dt>作者贡献</dt><dd>{(author.contributions ?? []).length ? (author.contributions ?? []).map((item, position) => <div key={position}>{item}</div>) : "未填写（选填）"}</dd><dt>ORCID</dt><dd>{author.orcid ? `${author.orcid}（未认证）` : "未填写（选填）"}</dd><dt>作者 / ORCID 来源</dt><dd className={styles.multiline}>{author.source_note || "未填写"}</dd></dl></article>)}</section>
    <OriginalText detail={detail} />
    <section className={styles.missing}><h2>缺项</h2>{detail.missing.length ? <ul>{detail.missing.map((item, index) => <li key={`${item.field}-${index}`}>{item.message}</li>)}</ul> : <p>当前版本无必填缺项。</p>}</section>
    <details><summary>版本摘要 SHA-256</summary><code>{detail.content_digest}</code></details>
    <VersionList key={`${detail.version_id}:${detail.verification?.id ?? ""}`} detail={detail} onUnavailable={onUnavailable} />
    <section className={styles.confirm}><label className={styles.checkbox}><input name="acknowledged" type="checkbox" checked={acknowledged} disabled={!allowed || busy} onChange={event => setAcknowledged(event.target.checked)} /><span>我已逐项核对本版元数据、作者、来源与完整原文，确认资料记录准确。</span></label><p className={styles.hint}>本次仅核对内部资料，不提交稿件，不代表作者身份认证或伦理声明。</p><button className={styles.primary} disabled={!allowed || !acknowledged || busy} onClick={() => void onConfirm()}>{confirming ? "确认中…" : detail.verified ? "本版已核对" : "确认本版资料"}</button>{detail.missing.length > 0 && <p className={styles.hint}>补齐缺项并保存新版本后，才能确认。</p>}</section>
  </div></>;
}
