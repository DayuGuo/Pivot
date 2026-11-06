import type { NextRequest } from "next/server";

// Resolve the private API origin at request time so one build works locally and in Compose.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// One Next.js server process in the private VPS image. Refuse before buffering uploads.
let heavyRequests = 0;
type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, process.env.INTERNAL_API_URL || "http://127.0.0.1:8100");
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of ["content-type", "cookie", "x-csrf-token", "origin", "sec-fetch-site"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const formalImport = /^publishing\/manuscripts\/[^/]+\/document-imports$/.test(path.join("/"));
  const heavy = formalImport || ["editorial-demo/chat", "publishing/chat"].includes(path.join("/")) || /^dossiers\/[^/]+\/(chat|imports|revision-checks)$/.test(path.join("/"));
  const admitted = heavy && request.method === "POST";
  if (admitted && heavyRequests >= 1) return Response.json({ detail: "正在处理另一份资料，请稍后重试；本次请求尚未执行。" }, { status: 429, headers: { "Retry-After": "2", "Cache-Control": "no-store" } });
  if (admitted) heavyRequests++;
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([
        AbortSignal.timeout(heavy ? 75_000 : 30_000),
        // Cancel obsolete reads across the proxy; an abandoned POST still has
        // an unknown outcome and must only be recovered with its original UUID.
        ...(request.method === "GET" ? [request.signal] : []),
      ]),
    });
    const resultHeaders = new Headers({ "Cache-Control": "no-store" });
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) resultHeaders.set("retry-after", retryAfter);
    const contentType = upstream.headers.get("content-type");
    if (contentType) resultHeaders.set("content-type", contentType);
    const digest = upstream.headers.get("x-content-sha256");
    if (digest) resultHeaders.set("x-content-sha256", digest);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) resultHeaders.set("content-disposition", disposition);
    for (const cookie of upstream.headers.getSetCookie()) resultHeaders.append("set-cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers: resultHeaders });
  } catch {
    return Response.json({ detail: "出版服务暂时不可用，请检查后端运行状态后重试。" }, { status: 502 });
  } finally { if (admitted) heavyRequests--; }
}
export const GET = proxy;
export const POST = proxy;

export const PATCH = proxy;
export const PUT = proxy;
