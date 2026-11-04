"use client";
import Link from "next/link";
import { useHistoryPages } from "./use-history-pages";
import { LibraryError } from "./api";
import type { DocumentImportItem } from "./types";
import styles from "./library.module.css";

export default function ImportHistory({ dossierId, revision, onUnavailable }: { dossierId: string; revision: number; onUnavailable: (error: LibraryError) => void }) {
  const { page, loading, error, load } = useHistoryPages<DocumentImportItem>(`/api/dossiers/${encodeURIComponent(dossierId)}/imports`, null, onUnavailable);
  const items = page?.items;
  return <details className={styles.importHistory} onToggle={event => { if (event.currentTarget.open && page === null && !loading && !error) void load(); }}><summary>导入记录</summary>
    {loading && <p role="status">正在读取导入记录…</p>}
    {error && <div><p role="alert">{error}</p><button type="button" disabled={loading} onClick={() => void load()}>重试导入记录</button></div>}
    {items?.length === 0 && <p className={styles.hint}>尚未导入 PDF 或 Word 稿件。</p>}
    {items?.map(item => <Link key={item.id} href={`/library/imports/${item.id}?dossier=${dossierId}`}><strong>{item.filename}</strong><span>{item.confirmed_version_id ? "已导入" : item.base_revision === revision ? "待核对" : "待核对 · 当前资料已更新"}</span><small>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}</small></Link>)}
    {page?.next_cursor && !error && <button type="button" disabled={loading} onClick={() => void load()}>加载更多导入记录</button>}
  </details>;
}
