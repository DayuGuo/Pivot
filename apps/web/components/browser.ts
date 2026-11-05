// Capability helpers, never authentication or business policy. No global polyfills.
export function requestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  // getRandomValues also works in older browsers and HTTP local previews.
  if (!globalThis.crypto?.getRandomValues) throw new Error('浏览器缺少安全随机数支持，请升级浏览器。');
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function readStorage(kind: 'localStorage' | 'sessionStorage', key: string): string | null {
  try { return window[kind].getItem(key); } catch { return null; }
}

export function writeStorage(kind: 'localStorage' | 'sessionStorage', key: string, value: string) {
  try { window[kind].setItem(key, value); } catch { /* Optional persistence never blocks live work. */ }
}

export async function withRequestTimeout<T>(milliseconds: number, caller: AbortSignal | null | undefined, request: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const control = new AbortController();
  const cancel = () => control.abort(caller?.reason);
  if (caller?.aborted) cancel(); else caller?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => control.abort(new DOMException('Request timed out', 'TimeoutError')), milliseconds);
  try {
    if (control.signal.aborted) throw control.signal.reason ?? new DOMException('Request aborted', 'AbortError');
    // Keep the deadline until the callback consumes the response body too.
    return await request(control.signal);
  } finally { clearTimeout(timer); caller?.removeEventListener('abort', cancel); }
}

export async function sha256Bytes(bytes: ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('原文校验需要 HTTPS 或 localhost，请使用安全连接。');
  return Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('');
}

export function warnBeforeUnload(event: BeforeUnloadEvent) {
  event.preventDefault(); event.returnValue = 'true';
}
