"use client";

import { useEffect, useRef, useState } from "react";
import { LibraryError, readJSON } from "./api";
import type { FeedbackContext } from "./claim-feedback";
import type { Session } from "./types";
import styles from "./library.module.css";

type EvaluationPackage = { schema: string; package_id: string; source: { version_id: string }; claims: unknown[] };

export default function EvaluationExport({ context, answerId, versionId }: { context: FeedbackContext; answerId: string; versionId: string }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const alive = useRef(true), running = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function requireSameSession() {
    const current = await readJSON<Session>("/api/publishing/session");
    const old = context.session;
    if (current.user.id !== old.user.id || current.journal.id !== old.journal.id || current.user.role !== old.user.role || current.csrf_token !== old.csrf_token) throw new LibraryError(401, "身份已变化，请重新登录后下载。");
  }
  async function download() {
    if (running.current) return;
    running.current = true; setBusy(true); setError(""); setNotice("");
    try {
      await requireSameSession();
      if (!alive.current) return;
      const result = await readJSON<EvaluationPackage>(`/api/dossiers/${context.dossierId}/answers/${answerId}/evaluation-package`);
      if (!alive.current) return;
      if (result.schema !== "claim-evaluation-package.v1" || !/^[0-9a-f-]{36}$/i.test(result.package_id) || result.source?.version_id !== versionId || !Array.isArray(result.claims) || !result.claims.length) throw new LibraryError(502, "评价包未完整收到，请重试下载。");
      // A cookie can change while the export waits; never download that old response.
      await requireSameSession();
      if (!alive.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `pivot-evaluation-${result.package_id}.json`;
      document.body.append(anchor); anchor.click(); anchor.remove();
      // Let the browser consume the object URL before releasing its bounded buffer.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("评价包已生成；包含全文与作者资料，AI判定已隐藏。仅用于获授权的独立核对。");
    } catch (e) {
      if (!alive.current) return;
      setError((e as Error).message);
      if (e instanceof LibraryError && [401, 403, 404].includes(e.status)) context.onDenied();
    } finally { running.current = false; if (alive.current) setBusy(false); }
  }
  return <div>
    <div className={styles.exportActions}>
      <a href={`/api/dossiers/${context.dossierId}/answers/${answerId}/review-summary`} download={`claim-review-${answerId}.json`}>下载复核摘要</a>
      <button type="button" disabled={busy} aria-busy={busy} onClick={() => void download()}>{busy ? "正在生成评价包…" : "下载独立评价包"}</button>
    </div>
    {error && <p role="alert">{error}</p>}{notice && <p className={styles.hint} role="status">{notice}</p>}
  </div>;
}
