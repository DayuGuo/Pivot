"use client";
import { warnBeforeUnload } from "../browser";
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { withRequestTimeout } from '../browser';
import { APIError, usePublishing } from './workspace';
import styles from './publishing.module.css';
type Segment = {
    kind: 'pdf_page' | 'docx_paragraph';
    number: number;
    start: number;
    end: number;
    text: string;
};
type Imported = {
    id: string;
    manuscript_id: string;
    version_id: string;
    base_revision: number;
    digest: string;
    purpose: string;
    filename: string;
    sha256: string;
    source_kind: string;
    source_note: string;
    text: string;
    segments: Segment[];
    warnings: string[];
    parser: string;
    material_scope: string;
    original_url: string;
    editable: boolean;
    confirmed_file_id: string | null;
    confirmed_range: {first_segment:number;last_segment:number}|null;
};
async function getImport(url: string, signal: AbortSignal) {
    return withRequestTimeout(15000, signal, async signal => {
    const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin', signal });
    const data = await response.json();
    if (!response.ok)
        throw new APIError(response.status, typeof data.detail === 'string' ? data.detail : '暂时无法读取导入记录，请重新载入。');
    return data as Imported;
    });
}
export default function FormalDocumentPage({ manuscriptId, importId }: {
    manuscriptId: string;
    importId: string;
}) {
    const { detail, selectedId, setReviewContext, session } = usePublishing();
    useEffect(() => { setReviewContext(manuscriptId); return () => setReviewContext(null); }, [manuscriptId, setReviewContext]);
    return <section className={styles.panel} aria-label="正式文件导入"><header className={styles.panelHeader}><h1>{importId === 'new' ? '导入 PDF / Word' : '核对导入文件'}</h1><Link href={`/publishing?manuscript=${manuscriptId}`}>返回稿件</Link></header>{importId === 'new' ? (detail?.id === manuscriptId && selectedId === manuscriptId ? <Upload key={`${session.journal.id}:${session.user.id}:${session.user.role}:${manuscriptId}:${detail.version?.id}`} detail={detail}/> : <p role="status">正在读取当前稿件…</p>) : <Review key={`${session.journal.id}:${session.user.id}:${session.user.role}:${manuscriptId}:${importId}`} manuscriptId={manuscriptId} importId={importId}/>}</section>;
}
function Upload({ detail }: {
    detail: NonNullable<ReturnType<typeof usePublishing>['detail']>;
}) {
    const { mutate, setUnsaved } = usePublishing();
    const router = useRouter();
    const [file, setFile] = useState<File | null>(null), [purpose, setPurpose] = useState('manuscript'), [sourceKind, setSourceKind] = useState('synthetic'), [materialScope, setMaterialScope] = useState('complete'), [note, setNote] = useState(''), [authorized, setAuthorized] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    const pending = useRef<object | null>(null);
    const [retryAvailable, setRetryAvailable] = useState(false);
    const dirty = !!file || !!note || authorized;
    useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
    useEffect(() => { if (!dirty)
        return; const warn = warnBeforeUnload; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty]);
    if (!detail.can_edit_intake || !detail.version)
        return <p>只有稿件负责人能在可编辑草稿中准备导入。</p>;
    const version = detail.version;
    function edited() { pending.current = null; setRetryAvailable(false); setError(''); }
    async function upload(retry = false) {
        if (busy || (!retry && (!file || !authorized || note.trim().length < 5)))
            return;
        setBusy(true);
        setError('');
        try {
            if (!retry || !pending.current) {
                if (!file || file.size > 5 * 1024 * 1024 || !file.size)
                    throw Error('请选择不超过5 MiB的PDF或DOCX。');
                const bytes = new Uint8Array(await file.arrayBuffer());
                let binary = '';
                for (let start = 0; start < bytes.length; start += 8192)
                    binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
                if (!alive.current)
                    return;
                pending.current = { expected_revision: detail.revision, version_id: version.id, purpose, filename: file.name, content_base64: btoa(binary), authorized_material: true, source_kind: sourceKind, material_scope: materialScope, source_note: note.trim() };
            }
            const out = await mutate<{
                import_id: string;
            }>(`/manuscripts/${detail.id}/document-imports`, pending.current!);
            if (!alive.current)
                return;
            setUnsaved(false);
            router.replace(`/publishing/document-imports/${detail.id}/${out.import_id}`);
        }
        catch (e) {
            if (!alive.current)
                return;
            setError((e as Error).message);
            if (e instanceof APIError && [403, 404, 409, 422].includes(e.status))
                pending.current = null;
            setRetryAvailable(!!pending.current);
        }
        finally {
            if (alive.current)
                setBusy(false);
        }
    }
    return <><PendingImports manuscriptId={detail.id}/><form className={styles.fields} autoComplete="off" onSubmit={e => { e.preventDefault(); void upload(); }}><p>提取结果先由你核对，再保存到本稿 v{version.version_no}。作者资料和声明沿用稿件已保存内容。</p><label htmlFor="document-purpose">导入用途</label><select id="document-purpose" name="purpose" disabled={busy} value={purpose} onChange={e => { setPurpose(e.target.value); edited(); }}><option value="manuscript">完整稿件</option><option value="blinded_manuscript">匿名稿件</option><option value="response">修回说明</option></select><label htmlFor="formal-document-file">选择 PDF / Word</label><input id="formal-document-file" name="document" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy} onChange={e => { setFile(e.target.files?.[0] ?? null); edited(); }}/><label htmlFor="document-source-kind">资料来源</label><select id="document-source-kind" name="source_kind" value={sourceKind} disabled={busy} onChange={e => { setSourceKind(e.target.value); edited(); }}><option value="synthetic">合成测试资料</option><option value="public_authorized">公开 / 已获授权资料</option></select><label htmlFor="document-material-scope">材料范围</label><select id="document-material-scope" name="material_scope" value={materialScope} disabled={busy} onChange={e => { setMaterialScope(e.target.value); edited(); }}><option value="complete">完整稿件 / 完整回复</option><option value="excerpt">仅提供节选</option></select><label htmlFor="document-source-note">来源与授权说明</label><textarea id="document-source-note" name="source_note" rows={3} required minLength={5} maxLength={2000} value={note} disabled={busy} onChange={e => { setNote(e.target.value); edited(); }}/><label className={styles.checkbox}><input type="checkbox" name="authorized_material" checked={authorized} disabled={busy} onChange={e => { setAuthorized(e.target.checked); edited(); }}/>我有权使用此资料，不含真实保密稿件或未经授权的数据</label>{error && <p role="alert" className={styles.error}>{error}{retryAvailable && <button type="button" disabled={busy} onClick={() => void upload(true)}>重试同一导入</button>}</p>}<button type="submit" disabled={busy || !file || !authorized || note.trim().length < 5}>{busy ? '正在提取…' : '提取并打开核对页'}</button><p className={styles.subtle}>文字层PDF / DOCX，原件上限5 MiB。扫描件需先OCR；Word需先处理修订和批注。</p></form></>;
}
function PendingImports({ manuscriptId }: {
    manuscriptId: string;
}) {
    const [items, setItems] = useState<{
        id: string;
        filename: string;
        editable: boolean;
    }[]>([]), [cursor, setCursor] = useState<string | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
    const alive = useRef(true);
    useEffect(() => { let ignore = false; const control = new AbortController(); alive.current = true; withRequestTimeout(15000, control.signal, signal => fetch(`/api/publishing/manuscripts/${manuscriptId}/document-imports`, { cache: 'no-store', credentials: 'same-origin', signal }).then(r => { if (!r.ok)
        throw Error('无法载入待核对导入，请刷新重试。'); return r.json(); })).then(data => { if (!ignore) {
        setItems(data.items);
        setCursor(data.next_cursor);
    } }).catch(e => { if (!ignore)
        setError(e.message); }); return () => { ignore = true; alive.current = false; control.abort(); }; }, [manuscriptId]);
    async function more() { if (!cursor || busy)
        return; setBusy(true); setError(''); try {
        const data = await withRequestTimeout(15000, null, async signal => {
        const r = await fetch(`/api/publishing/manuscripts/${manuscriptId}/document-imports?cursor=${encodeURIComponent(cursor)}`, { cache: 'no-store', credentials: 'same-origin', signal });
        if (!r.ok)
            throw Error('无法加载更多，请重试。');
        return r.json();
        });
        if (alive.current) {
            setItems(old => [...old, ...data.items.filter((next: {
                    id: string;
                }) => !old.some(item => item.id === next.id))]);
            setCursor(data.next_cursor);
        }
    }
    catch (e) {
        if (alive.current)
            setError((e as Error).message);
    }
    finally {
        if (alive.current)
            setBusy(false);
    } }
    return <>{items.length > 0 && <section><h2>继续核对</h2><ul>{items.map(item => <li key={item.id}><Link href={`/publishing/document-imports/${manuscriptId}/${item.id}`}>{item.filename}{item.editable ? '' : ' · 稿件内容已变化'}</Link></li>)}</ul>{cursor && <button disabled={busy} onClick={() => void more()}>{busy ? '正在载入…' : '更多待核对导入'}</button>}</section>}{error && <p role="alert">{error}</p>}</>;
}
const warningLabels: Record<string, string> = {docx_paragraph_numbers_are_extraction_order_not_page_numbers:'Word段落号按提取顺序计数，不是页码。',tables_notes_headers_footers_are_linearized:'表格、脚注和页眉页脚已展开为文本，请核对顺序。',external_hyperlink_targets_ignored:'未跟随文件中的外部链接。',docx_cached_fields_not_updated:'域结果沿用文档保存的内容，请核对目录和交叉引用。',docx_pagination_not_rendered:'未重排Word页码，请按段落定位。',docx_images_and_figures_not_interpreted:'图片和图形未作语义识别，请对照原件。', pdf_text_reading_order_requires_review: '请核对PDF多栏和段落的阅读顺序。', figures_images_and_equations_not_interpreted: '图片与公式未作语义识别，请对照原件。', pdf_initial_page_destination_ignored: '已忽略PDF初始页面跳转。', pdf_winansi_bullet_encoding_normalized: '项目符号按PDF字体编码规范提取，请对照原件核对。', docx_list_markers_not_rendered: 'Word自动列表标记未作排版还原，请核对顺序。' };
function Review({ manuscriptId, importId }: {
    manuscriptId: string;
    importId: string;
}) {
    const { mutate, refresh, setUnsaved, setReviewContext } = usePublishing();
    const [item, setItem] = useState<Imported | null>(null), [first, setFirst] = useState(1), [last, setLast] = useState(1), [original, setOriginal] = useState(false), [text, setText] = useState(false), [scope, setScope] = useState(false), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState('');
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    const sequence = useRef(0), controller = useRef<AbortController | null>(null), pending = useRef<object | null>(null);
    const load = useCallback(async () => { controller.current?.abort(); const abort = new AbortController(); controller.current = abort; const generation = ++sequence.current; setLoading(true); setItem(null); setOriginal(false); setText(false); setScope(false); pending.current = null; setError(''); try {
        const next = await getImport(`/api/publishing/manuscripts/${manuscriptId}/document-imports/${importId}`, abort.signal);
        if (generation === sequence.current && !abort.signal.aborted) {
            setItem(next);
            setReviewContext(manuscriptId);
            setFirst(next.confirmed_range?.first_segment ?? 1);
            setLast(next.confirmed_range?.last_segment ?? next.segments.length);
        }
    }
    catch (e) {
        if (!abort.signal.aborted && generation === sequence.current) {
            setError((e as Error).message);
            if (e instanceof APIError && [401,403,404].includes(e.status)) setReviewContext(null);
        }
    }
    finally {
        if (!abort.signal.aborted && generation === sequence.current)
            setLoading(false);
    } }, [manuscriptId, importId, setReviewContext]);
    // External source loading deliberately resets old material and all acknowledgments.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => { void load(); const request = controller.current; return () => request?.abort(); }, [load]);
    const dirty = !!item?.editable && (original || text || scope || first !== 1 || last !== item.segments.length);
    useEffect(() => { setUnsaved(dirty); return () => setUnsaved(false); }, [dirty, setUnsaved]);
    useEffect(() => { if (!dirty)
        return; const warn = warnBeforeUnload; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty]);
    function range(changedFirst: number, changedLast: number) { setFirst(changedFirst); setLast(changedLast); setScope(false); setText(false); pending.current = null; }
    async function confirm() { if (!item || busy)
        return; setBusy(true); setError(''); try {
        pending.current ??= { expected_revision: item.base_revision, digest: item.digest, first_segment: first, last_segment: last, acknowledged_original: original, acknowledged_text: text, acknowledged_scope: scope };
        await mutate(`/manuscripts/${manuscriptId}/document-imports/${importId}/confirmations`, pending.current);
        if (!alive.current)
            return;
        setUnsaved(false);
        await load();
        if (alive.current) void refresh();
    }
    catch (e) {
        if (!alive.current)
            return;
        setError((e as Error).message);
        if (e instanceof APIError && [401, 403, 404, 409].includes(e.status)) {
            setItem(null);
            setOriginal(false);
            setText(false);
            setScope(false);
            pending.current = null;
            if ([401, 403, 404].includes(e.status))
                setReviewContext(null);
        }
    }
    finally {
        if (alive.current)
            setBusy(false);
    } }
    if (!item)
        return <><p role={error ? 'alert' : 'status'}>{error || '正在载入待核对原件…'}</p><button disabled={loading || busy} onClick={() => void load()}>重新载入导入记录</button></>;
    const valid = Number.isInteger(first) && Number.isInteger(last) && first >= 1 && last >= first && last <= item.segments.length;
    const selected = valid ? item.segments.slice(first - 1, last).map(segment => segment.text).join('\n\n') : '';
    const unit = item.segments[0].kind === 'pdf_page' ? '页' : '段落';
    return <div className={styles.fields}><p>{item.filename} · {item.segments.length} {unit} · {item.confirmed_file_id ? '已确认保存' : '待负责人核对'}</p><a href={item.original_url} target="_blank" rel="noopener noreferrer">查看完整原件</a><p className={styles.subtle}>{item.source_note}</p>{item.material_scope === 'excerpt' && <p className={styles.notice}>本次仅提供节选，不能据未提供部分断言作者未回应。</p>}{item.warnings.length>0 && <ul className={`${styles.notice} ${styles.missing}`}>{item.warnings.map((w,i)=><li key={i}>{warningLabels[w]??'部分格式需对照原件核对。'}</li>)}</ul>}{item.confirmed_file_id ? <p role="status">已保存到绑定草稿。正式提交仍需另行审核；当前文件如已替换，请以稿件现行文件为准。</p> : !item.editable ? <p className={styles.notice}>稿件版本或处理进度已变化。此导入不可再确认，请返回当前稿件重新准备。</p> : <p>请核对正文范围，排除合并在末尾的评审记录或作者回复。完整原件保留；只有下列范围进入所选用途。确认前，对话仍以稿件现行文件为依据。</p>}<label htmlFor="scope-first">正文起始{unit}</label><input id="scope-first" name="first_segment" type="number" min={1} max={item.segments.length} value={first} disabled={busy || !item.editable} onChange={e => range(Number(e.target.value), last)}/><label htmlFor="scope-last">正文结束{unit}</label><input id="scope-last" name="last_segment" type="number" min={first} max={item.segments.length} value={last} disabled={busy || !item.editable} onChange={e => range(first, Number(e.target.value))}/>{!valid && <p role="alert">请选择有效的正文范围。</p>}<label htmlFor="formal-extracted-text">{item.confirmed_file_id?'已保存的提取全文':'待保存的提取全文'}</label><textarea id="formal-extracted-text" name="extracted_text" rows={14} readOnly value={selected}/>{item.editable && <><label className={styles.checkbox}><input type="checkbox" name="acknowledged_original" checked={original} disabled={busy} onChange={e => { setOriginal(e.target.checked); pending.current = null; }}/>我已核对原件及其来源授权</label><label className={styles.checkbox}><input type="checkbox" name="acknowledged_text" checked={text} disabled={busy} onChange={e => { setText(e.target.checked); pending.current = null; }}/>我已对照原件核对提取全文，没有漏页或漏段</label><label className={styles.checkbox}><input type="checkbox" name="acknowledged_scope" checked={scope} disabled={busy} onChange={e => { setScope(e.target.checked); pending.current = null; }}/>我已核对所选范围符合文件用途，不混入评审附录或其他材料</label><button disabled={busy || !valid || !original || !text || !scope} onClick={() => void confirm()}>{busy ? '正在确认保存…' : '确认导入到当前草稿'}</button></>}{error && <p role="alert" className={styles.error}>{error}</p>}<details className={styles.hash}><summary>原件与提取快照</summary><code>{item.sha256}</code><p>{item.parser}</p></details></div>;
}
