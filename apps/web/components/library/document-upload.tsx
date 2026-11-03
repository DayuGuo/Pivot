"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Upload } from "./types";
import styles from "./library.module.css";

export default function DocumentUpload({ busy, onUpload, onCancel, onDirty }: {
  busy: boolean; onUpload: (file: Upload) => Promise<void>; onCancel: () => void; onDirty: (value: boolean) => void;
}) {
  const [file, setFile] = useState<Upload | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { ++generation.current; }, []);
  async function selectFile(value: File | undefined) {
    const current = ++generation.current;
    setFile(null); setError(""); setAuthorized(false); setReading(false); onDirty(false);
    if (!value) return;
    if (!/\.(pdf|docx)$/i.test(value.name) || !value.size || value.size > 5 * 1024 * 1024) {
      setError(/\.doc$/i.test(value.name) ? "请先将旧版 .doc 另存为 .docx 后再上传。" : "请选择非空的 PDF 或 Word .docx 文件，最大 5 MiB。"); return;
    }
    setReading(true);
    try {
      const bytes = new Uint8Array(await value.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      if (current !== generation.current) return;
      setFile({ filename: value.name, content_base64: btoa(binary) }); onDirty(true);
    } catch { if (current === generation.current) setError("无法读取文件，请重新选择本机文件后重试。"); }
    finally { if (current === generation.current) setReading(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !authorized || reading || busy) return;
    void onUpload(file);
  }
  return <><div className={styles.materialHeader}><h2>导入 PDF / Word</h2><button type="button" disabled={busy} onClick={onCancel}>取消</button></div>
    <form className={styles.form} onSubmit={submit}>
      <fieldset disabled={busy || reading}>
        <label>PDF 或 Word 稿件<input name="document-file" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-describedby="document-upload-help document-upload-error" onChange={event => void selectFile(event.target.files?.[0])} /></label>
        <p id="document-upload-help" className={styles.hint}>{reading ? "正在读取文件…" : file ? file.filename : "PDF / Word .docx，最大 5 MiB。提取完成后先核对，不会直接覆盖当前版本。"}</p>
        <label className={styles.checkbox}><input name="document-authorized" type="checkbox" checked={authorized} onChange={event => { setAuthorized(event.target.checked); onDirty(!!file); }} /><span>我确认文件为合成或公开已获授权资料，不包含保密稿件。</span></label>
      </fieldset>
      <p className={styles.hint}>扫描件、加密文件或提取不完整的稿件需要先处理后再导入。</p>
      {error && <p id="document-upload-error" className={styles.fieldError} role="alert">{error}</p>}
      <button className={styles.primary} type="submit" disabled={busy || reading || !file || !authorized}>{busy ? "正在提取稿件…" : "提取并打开核对表单"}</button>
    </form></>;
}
