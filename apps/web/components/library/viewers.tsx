import Link from "next/link";
import type { Dossier } from "./types";
import styles from "./library.module.css";

import { fileDownloadURL } from "./api";
export function OriginalText({ detail }: { detail: Dossier }) {
  const url = detail.file && fileDownloadURL(detail.file.download_url);
  return detail.file ? <section className={styles.original}><div className={styles.originalHeading}><h2>{detail.file.filename}</h2>{url && <a href={url} download>下载原文</a>}</div><p className={styles.hint}>{detail.file.media_type} · {new Intl.NumberFormat("zh-CN").format(detail.file.byte_size)} 字节</p><details><summary>文件 SHA-256</summary><code>{detail.file.sha256}</code></details><pre>{detail.file.text}</pre></section> : <p className={styles.hint}>尚未上传原文，请在资料中选择 TXT 或 Markdown 文件。</p>;
}
export function VersionList({ detail }: { detail: Dossier }) {
  return <section className={styles.versions}><h2>版本记录</h2>{detail.versions.map(version => <Link key={version.id} href={`/library/review/${version.id}?dossier=${detail.id}`}><span>v{version.number} · {version.verified ? "已核对" : "待核对"}</span><strong>{version.title || "未命名资料"}</strong><small>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(version.created_at))}</small></Link>)}</section>;
}
