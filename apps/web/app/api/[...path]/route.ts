import type { NextRequest } from "next/server";

// Resolve the private API origin at request time so one build works locally and in Compose.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
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
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(["editorial-demo/chat", "publishing/chat"].includes(path.join("/")) ? 75_000 : 30_000),
    });
    const resultHeaders = new Headers({ "Cache-Control": "no-store" });
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
  }
}
export const GET = proxy;
export const POST = proxy;

export const PATCH = proxy;
export const PUT = proxy;
