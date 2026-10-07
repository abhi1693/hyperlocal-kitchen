/** Restricted same-origin admin gateway, following DevFeed's cookie/CSRF pattern. */
import "server-only";
import { adminApiOrigin, adminWebOrigin } from "./config";
const safe = new Set(["GET", "HEAD", "OPTIONS"]);
export async function gateway(request: Request, segments: string[]) {
  if (!segments.length || segments.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part)))
    return Response.json({ detail: "Not found" }, { status: 404 });
  const path = "/api/v1/" + segments.join("/");
  try {
    if (!safe.has(request.method) && request.headers.get("origin") !== adminWebOrigin())
      return Response.json({ detail: "Invalid request origin" }, { status: 403 });
    const headers = new Headers({ Accept: "application/json" });
    for (const name of ["cookie", "content-type", "origin", "x-csrf-token", "idempotency-key"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    let body: ArrayBuffer | undefined;
    if (!safe.has(request.method)) {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader)
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 1000000) {
            await reader.cancel();
            return Response.json({ detail: "Request too large" }, { status: 413 });
          }
          chunks.push(value);
        }
      const buffer = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        buffer.set(chunk, offset);
        offset += chunk.length;
      }
      body = buffer.buffer;
    }
    const upstream = await fetch(`${adminApiOrigin()}${path}${new URL(request.url).search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]),
    });
    const resultHeaders = new Headers({
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
    });
    for (const name of ["content-type", "location", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      resultHeaders.append("Set-Cookie", cookie);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: resultHeaders,
    });
  } catch {
    return Response.json(
      { detail: "Admin service unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
