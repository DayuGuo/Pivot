"use client";
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FeedbackContext } from './claim-feedback';
import { LibraryError, readJSON, requireLibrarySession } from './api';
import { verdictLabel, type EvaluationDetail, type EvaluationCitation, type ReturnReceipt, type Assessment } from './evaluation-types';
import styles from './library.module.css';
type HistoryItem = ReturnReceipt & { assessments: Record<string, Assessment> };
type Preview = {
    digest: string;
    assessments: Record<string, Assessment>;
    answered: number;
    unanswered: number;
};
export default function EvaluationReview({ context, packageId }: {
    context: FeedbackContext;
    packageId: string;
}) {
    const [detail, setDetail] = useState<EvaluationDetail | null>(null), [packet, setPacket] = useState<unknown>(null), [preview, setPreview] = useState<Preview | null>(null), [checked, setChecked] = useState<string[]>([]), [ack, setAck] = useState(false), [busy, setBusy] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState(''), [citation, setCitation] = useState<EvaluationCitation | null>(null), [history, setHistory] = useState<HistoryItem[]>([]), [cursor, setCursor] = useState<number | null>(null);
    const alive = useRef(true), running = useRef(false), generation = useRef(0), pending = useRef<string | null>(null), mark = useRef<HTMLElement>(null), input = useRef<HTMLInputElement>(null);
    const key = `evaluation:${packageId}`, url = `/api/dossiers/${context.dossierId}/evaluations/${packageId}`, onDirty = context.onDirty;
    const denied = useRef(context.onDenied);
    const failure = useCallback((e: unknown) => { if (!alive.current)
        return; setError((e as Error).message); if (e instanceof LibraryError && [401, 403, 404].includes(e.status)) {
        setDetail(null);
        setPacket(null);
        setPreview(null);
        denied.current();
    } }, []);
    const load = useCallback(async () => { if (running.current)
        return; running.current = true; try {
        const next = await readJSON<EvaluationDetail>(url);
        if (!alive.current)
            return;
        if (next.id !== packageId || next.packet.package_id !== packageId || next.packet.source.version_id !== next.version_id)
            throw new LibraryError(409, '评价包来源不一致');
        setDetail(next);
        setError('');
        setHistory([]);
        setCursor(null);
        setCitation(null);
        setPacket(null);
        setPreview(null);
        setAck(false);
        setChecked([]);
        pending.current = null;
        onDirty(key, false);
    }
    catch (e) {
        failure(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
    } }, [url, packageId, onDirty, key, failure]);
    useEffect(() => { alive.current = true; queueMicrotask(() => { if (alive.current) void load(); }); return () => { alive.current = false; onDirty(key, false); }; }, [load, key, onDirty]); // Component key binds the dossier, package and session.
    useEffect(() => { if (citation) {
        mark.current?.focus({ preventScroll: true });
        mark.current?.scrollIntoView({ block: 'center' });
    } }, [citation]);
    async function selectFile(file: File | undefined) { if (!file || running.current)
        return; const epoch = ++generation.current; setPreview(null); setPacket(null); setAck(false); setChecked([]); setNotice(''); setError(''); pending.current = null; running.current = true; setBusy(true); try {
        if (file.size > 2 * 1024 * 1024)
            throw new LibraryError(413, '评价文件最多2MiB，请选择原登记包。');
        const content = await file.text();
        if (!alive.current || epoch !== generation.current)
            return;
        let value: unknown;
        try {
            value = JSON.parse(content);
        }
        catch {
            throw new LibraryError(422, '文件不是有效JSON，请仅填写登记包中的assessment。');
        }
        await requireLibrarySession(context.session);
        if (!alive.current)
            return;
        const result = await readJSON<Preview>(url + '/preview', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': context.session.csrf_token }, body: JSON.stringify({ packet: value }) });
        if (!alive.current || epoch !== generation.current)
            return;
        if (!/^[0-9a-f]{64}$/.test(result.digest) || !result.assessments || !detail || detail.packet.claims.some(c => !Object.hasOwn(result.assessments, c.id)))
            throw new LibraryError(502, '未完整收到预览，请重新选择文件。');
        setPacket(value);
        setPreview(result);
        onDirty(key, true);
    }
    catch (e) {
        failure(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
        if (input.current)
            input.current.value = '';
    } }
    async function confirm() { if (!detail || !preview || !packet || running.current)
        return; running.current = true; setBusy(true); setError(''); pending.current ??= crypto.randomUUID(); try {
        await requireLibrarySession(context.session);
        if (!alive.current)
            return;
        const result = await readJSON<ReturnReceipt>(url + '/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': context.session.csrf_token }, body: JSON.stringify({ request_id: pending.current, packet, preview_digest: preview.digest, expected_return_id: detail.latest?.id ?? null, acknowledged: ack, acknowledged_claims: checked.slice().sort() }) });
        if (!alive.current)
            return;
        if (!/^[0-9a-f-]{36}$/i.test(result.id) || result.package_id !== packageId || result.version_id !== detail.version_id || result.digest !== preview.digest)
            throw new LibraryError(502, '未完整收到确认回执；保持文件不变，再次确认以恢复同一请求。');
        setDetail({ ...detail, latest: result });
        setHistory([]);
        setCursor(null);
        setCitation(null);
        setPreview(null);
        setPacket(null);
        setAck(false);
        setChecked([]);
        pending.current = null;
        onDirty(key, false);
        setNotice('评价回传已确认保存；原回答和稿件决定保持不变。');
    }
    catch (e) {
        failure(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
    } }
    async function downloadRegistered() {
        if (running.current || !detail) return;
        running.current = true; setBusy(true); setError('');
        try {
            await requireLibrarySession(context.session);
            if (!alive.current) return;
            const value = await readJSON<EvaluationDetail['packet']>(url + '/file');
            if (!alive.current) return;
            if (value.package_id !== packageId || value.source.version_id !== detail.version_id) throw new LibraryError(409, '下载来源与登记版本不符');
            await requireLibrarySession(context.session);
            if (!alive.current) return;
            const objectURL = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
            const anchor = document.createElement('a'); anchor.href = objectURL; anchor.download = `pivot-evaluation-${packageId}.json`;
            document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
        } catch(e) { failure(e); }
        finally { running.current = false; if (alive.current) setBusy(false); }
    }
    async function older(before?: number) { if (running.current)
        return; running.current = true; setBusy(true); setError(''); try {
        const result = await readJSON<{
            items: HistoryItem[];
            next_cursor: number | null;
        }>(url + `/returns${before ? `?before=${before}` : ''}`);
        if (alive.current) {
            setHistory(before ? old => [...old, ...result.items] : result.items);
            setCursor(result.next_cursor);
        }
    }
    catch (e) {
        failure(e);
    }
    finally {
        running.current = false;
        if (alive.current)
            setBusy(false);
    } }
    const source = detail?.packet.source;
    let text = source?.text ?? '';
    if (citation?.kind === 'metadata' && source) {
        let value: unknown = source.data;
        for (const part of citation.field_path?.split('.') ?? [])
            value = value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : null;
        text = typeof value === 'string' || typeof value === 'boolean' ? String(value) : '';
    }
    const chars = Array.from(text), valid = citation && chars.slice(citation.start, citation.end).join('') === citation.quote;
    return <><div className={styles.materialHeader}><h2>核对独立评价</h2><Link href={`/library?dossier=${context.dossierId}`}>返回资料</Link></div><div className={styles.review}>
 {!detail ? <p role="status">{busy ? '正在载入评价包…' : '尚未载入评价包，请重试。'}</p> : <><h2>{detail.evaluator_code} · v{detail.version_no}</h2><p className={styles.hint}>{detail.is_current ? '本包绑定当前保存版本。' : '本包绑定历史版本，不继承到当前版本。'} 评价代号不是身份认证。</p><button type="button" disabled={busy} onClick={() => void downloadRegistered()}>下载已登记评价包</button><p>填写每条 assessment.verdict 与 note，再上传结果。原文、作者、结论和引文均不能修改。未评价项保留 null 和空理由。</p>
 <label>上传评价结果<input ref={input} type="file" accept=".json,application/json" disabled={busy} onChange={e => void selectFile(e.target.files?.[0])}/></label>
 {preview && <><p role="status">预览：{preview.answered} 条已评价，{preview.unanswered} 条未评价；尚未保存。</p>{detail.packet.claims.map((c, index) => <section key={c.id}><h3>结论 {index + 1}</h3><p>{c.text}</p><p>{preview.assessments[c.id].verdict ? verdictLabel[preview.assessments[c.id].verdict!] : '未评价'}</p><p>{preview.assessments[c.id].note}</p>{c.citations.map((q, i) => <div key={i}><blockquote>{q.quote}</blockquote><button type="button" onClick={() => setCitation(q)}>定位评价引文：{index + 1}.{i + 1} {q.label}</button></div>)}<label className={styles.checkbox}><input type="checkbox" disabled={busy} checked={checked.includes(c.id)} onChange={e => { setChecked(e.target.checked ? [...checked, c.id] : checked.filter(id => id !== c.id)); setAck(false); }}/><span>已核对此项及其评价或未评价状态</span></label></section>)}
 <label className={styles.checkbox}><input type="checkbox" disabled={busy} checked={ack} onChange={e => setAck(e.target.checked)}/><span>本人已逐条核对本评价包、历史版本、完整意见和原文；仅确认回传记录，不作出版决定。</span></label><button type="button" className={styles.primary} disabled={busy || !ack || checked.length !== detail.packet.claims.length} onClick={() => void confirm()}>{busy ? '确认中…' : '确认评价回传'}</button></>}
 {citation && <section aria-label="评价原文定位"><h3>{citation.label}</h3>{valid ? <pre className={styles.locatedText}>{chars.slice(0, citation.start).join('')}<mark ref={mark} tabIndex={-1} aria-label="已定位评价原文">{chars.slice(citation.start, citation.end).join('')}</mark>{chars.slice(citation.end).join('')}</pre> : <p role="alert">引用与来源不符，请重新载入。</p>}</section>}
 <details><summary>完整原文与作者资料</summary><h3>{source?.data.title}</h3><p>{source?.data.abstract}</p><dl className={styles.facts}><dt>语言</dt><dd>{source?.data.language}</dd><dt>关键词</dt><dd>{source?.data.keywords.join('、')}</dd><dt>来源与授权</dt><dd>{source?.data.source_note}</dd></dl>{source?.data.authors.map((author,i)=><section key={i}><h3>{author.name}{author.corresponding?'（通讯作者）':''}</h3><p>{author.email}</p><p>{author.affiliations.join('、')}</p><p>{author.orcid?`ORCID ${author.orcid}（未认证）`:'ORCID未提供'}</p><p>{(author.contributions ?? []).join('、')}</p><p>{author.source_note}</p></section>)}<pre className={styles.locatedText}>{source?.text}</pre></details>
 <details><summary onClick={() => { if (!history.length)
            void older(); }}>回传历史</summary>{history.map(r => <details key={r.id}><summary>第 {r.return_no} 次 · {new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(r.created_at))}</summary>{detail.packet.claims.map(c => <section key={c.id}><p>{c.text}</p><p>{r.assessments[c.id]?.verdict ? verdictLabel[r.assessments[c.id].verdict!] : '未评价'}</p><p>{r.assessments[c.id]?.note}</p></section>)}</details>)}{cursor && <button type="button" disabled={busy} onClick={() => void older(cursor)}>更早回传</button>}</details>
 <details><summary>评价包摘要</summary><code>{detail.packet_digest}</code></details></>}
 {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}<button type="button" disabled={busy} onClick={() => { if (!preview || window.confirm('当前核对尚未保存，重新载入将清除预览。'))
        { setBusy(true); void load(); } }}>重新载入评价包</button>
 </div></>;
}
