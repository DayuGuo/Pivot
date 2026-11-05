"use client";

import {useEffect, useRef, useState} from 'react';
import { sha256Bytes, withRequestTimeout } from '../browser';
import styles from './revision-comparison.module.css';

export type SourceCitation = {
  file_id?: string; start?: number; end?: number; quote: string; sha256: string;
  original?: {sha256: string; download_url: string};
};
class SourceError extends Error {}

type Located = {before: string; quote: string; after: string; clipped: boolean};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const sha = /^[0-9a-f]{64}$/;

async function identity(signal: AbortSignal) {
  const response = await fetch('/api/publishing/session', {cache:'no-store', credentials:'same-origin', signal});
  if (!response.ok) throw new SourceError('身份或访问权限已变化，请重新载入对话。');
  const value = await response.json();
  return `${value.journal.id}:${value.user.id}:${value.user.role}`;
}

export default function CitationSource({citation, scopeKey}:{citation:SourceCitation; scopeKey:string}) {
  const [source,setSource] = useState<Located|null>(null), [busy,setBusy] = useState(false), [error,setError] = useState('');
  const alive = useRef(true), controller = useRef<AbortController|null>(null), mark = useRef<HTMLElement|null>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;controller.current?.abort();};},[]);
  useEffect(()=>{if(source){mark.current?.focus({preventScroll:true});mark.current?.scrollIntoView({block:'nearest'});}},[source]);
  const {file_id:fileId,start,end,original} = citation;
  if (!fileId || !uuid.test(fileId) || !sha.test(citation.sha256) || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start!<0 || end!<=start! || !original || !sha.test(original.sha256) || original.download_url!==`/api/publishing/files/${fileId}/original`) return null;

  async function locate() {
    if(busy)return;
    if(source){setSource(null);return;}
    const control = new AbortController();controller.current=control;
    setBusy(true);setError('');setSource(null);
    try {
      await withRequestTimeout(15000, control.signal, async signal => {
      if(await identity(signal)!==scopeKey)throw new SourceError('身份或访问权限已变化，请重新载入对话。');
      const responses=await Promise.all([fetch(`/api/publishing/files/${fileId}`,{cache:'no-store',credentials:'same-origin',signal}),fetch(original!.download_url,{cache:'no-store',credentials:'same-origin',signal})]);
      if(responses.some(r=>!r.ok))throw new SourceError('原文暂不可读，请重新载入对话后重试。');
      const [textBytes,originalBytes]=await Promise.all(responses.map(r=>r.arrayBuffer()));
      if (!globalThis.crypto?.subtle) throw new SourceError('原文校验需要 HTTPS 或 localhost，请使用安全连接。');
      if(textBytes.byteLength>1048576 || originalBytes.byteLength>5242880 || await sha256Bytes(textBytes)!==citation.sha256 || await sha256Bytes(originalBytes)!==original!.sha256)throw new SourceError('原文校验未通过，未展示未核实内容。');
      const characters=Array.from(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(textBytes));
      if(end!>characters.length || characters.slice(start,end).join('')!==citation.quote)throw new SourceError('引用与绑定版本不一致，请重新载入对话。');
      if(await identity(signal)!==scopeKey)throw new SourceError('身份或访问权限已变化，请重新载入对话。');
      if(alive.current && !signal.aborted)setSource({before:characters.slice(Math.max(0,start!-500),start).join(''),quote:citation.quote,after:characters.slice(end,end!+500).join(''),clipped:start!>500 || end!+500<characters.length});
      });
    } catch(failure) {if(alive.current && !control.signal.aborted)setError(failure instanceof DOMException && failure.name==='TimeoutError'?'读取超时，请重试定位原文。':failure instanceof SourceError?failure.message:'无法验证原文，请重试或下载原件核对。');}
    finally {control.abort();if(alive.current)setBusy(false);}
  }
  return <div><button type="button" aria-expanded={!!source} disabled={busy} onClick={()=>void locate()}>{busy?'正在定位…':source?'收起原文':'定位已核对全文'}</button>{busy&&<p role="status">正在核对版本与原件…</p>}{error&&<p role="alert">{error}</p>}{source&&<><pre className={styles.sourceText}>{source.before}<mark ref={mark} tabIndex={-1} aria-label="已定位原文引用" className={styles.sourceQuote}>{source.quote}</mark>{source.after}</pre>{source.clipped&&<p>显示引用附近的全文节选；完整原件可通过上方链接下载。</p>}</>}</div>;
}
