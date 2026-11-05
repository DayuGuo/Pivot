import { withRequestTimeout } from "../browser";
import type { Session } from "./types";
export class LibraryError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function readJSON<T>(path: string, init?: RequestInit): Promise<T> {
  try { return await withRequestTimeout(80_000, init?.signal, async signal => {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...init, signal });
    const body = await response.json().catch(() => null);
    if (response.ok && (!body || typeof body !== "object" || Array.isArray(body))) throw new LibraryError(502, "响应未完整收到，请重试恢复结果。");
    if (!response.ok) {
      const detail: unknown = body?.detail;
      const message = typeof detail === "string" ? detail : detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string" ? detail.message : response.status === 401 ? "登录已失效，请重新登录。" : response.status === 403 ? "当前身份无法访问这些内部资料。" : response.status === 404 ? "资料或版本不存在，或不在你的访问范围内。" : response.status === 429 ? "服务正在处理另一份资料，请稍后重试。" : response.status === 409 ? "资料已更新，请重新载入后核对。" : "操作未完成，请检查输入后重试。";
      throw new LibraryError(response.status, message);
    }
    return body as T;
  }); } catch (error) {
    if (error instanceof LibraryError || (error instanceof DOMException && error.name === "AbortError")) throw error;
    throw new LibraryError(0, "无法连接资料服务，请检查网络后重试。");
  }
}
export function fileDownloadURL(value: string): string | null {
  // Download only through this application's authenticated, same-origin proxy.
  if (!value.startsWith("/api/") || value.includes("\\")) return null;
  const url = new URL(value, "https://local.invalid");
  return url.origin === "https://local.invalid" ? `${url.pathname}${url.search}` : null;
}

export function dossierListURL(query = "", cursor?: string | null): string {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (cursor) params.set("cursor", cursor);
  const encoded = params.toString();
  return `/api/dossiers${encoded ? `?${encoded}` : ""}`;
}

export async function requireLibrarySession(previous: Session) {
  const current = await readJSON<Session>("/api/publishing/session");
  if (current.user.id !== previous.user.id || current.journal.id !== previous.journal.id || current.user.role !== previous.user.role || current.csrf_token !== previous.csrf_token) throw new LibraryError(401, "身份已变化，请重新登录核对。");
}
