import { auth } from "@/lib/better-auth";
import { signInternalIdentity } from "@/lib/internal-identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path?: string[] }> };

const hopByHopHeaders = new Set([
  "connection",
  "content-length",
  "cookie",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "authorization",
  "x-oopsnote-identity",
  "x-oopsnote-signature",
]);

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return Response.json({ detail: "Authentication required" }, { status: 401 });
  }
  if (session.user.role !== "admin" && session.user.role !== "user") {
    console.error("Better Auth returned an unsupported OopsNote role", session.user.role);
    return Response.json({ detail: "Account role is invalid" }, { status: 403 });
  }
  const role = session.user.role;
  const pathName = `/${(await context.params).path?.join("/") || ""}`.replace(/\/+/g, "/");
  const backendUrl = (process.env.OOPSNOTE_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const target = `${backendUrl}${pathName}${new URL(request.url).search}`;
  let identity;
  try {
    identity = signInternalIdentity({
      userId: session.user.id,
      role,
      method: request.method,
      path: pathName,
    });
  } catch (error) {
    console.error("BFF identity signing is not configured", error);
    return Response.json({ detail: "Internal identity is not configured" }, { status: 500 });
  }

  const headers = new Headers(request.headers);
  for (const header of headers.keys()) {
    if (hopByHopHeaders.has(header.toLowerCase())) headers.delete(header);
  }
  headers.set("x-oopsnote-identity", identity.encoded);
  headers.set("x-oopsnote-signature", identity.signature);
  headers.set("cache-control", "no-store");

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    signal: request.signal,
    duplex: "half",
  };
  try {
    const upstream = await fetch(target, init);
    const responseHeaders = new Headers(upstream.headers);
    for (const header of ["connection", "content-length", "keep-alive", "transfer-encoding"])
      responseHeaders.delete(header);
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("OopsNote backend proxy failed", error);
    return Response.json({ detail: "Backend is unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
