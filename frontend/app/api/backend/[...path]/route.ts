import { auth } from "@/lib/better-auth";
import { signInternalIdentity } from "@/lib/internal-identity";
import { markWorkspaceProvisioned, pendingProvisioning } from "@/lib/better-auth-registration";

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
  if (pathName.startsWith("/internal/")) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  const backendUrl = (process.env.OOPSNOTE_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const pending = pendingProvisioning(session.user.id);
  if (pending !== null) {
    const bootstrapPath = "/internal/members/provision-self";
    const bootstrapIdentity = signInternalIdentity({
      userId: session.user.id,
      role,
      method: "POST",
      path: bootstrapPath,
    });
    try {
      const bootstrapResponse = await fetch(`${backendUrl}${bootstrapPath}`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-oopsnote-identity": bootstrapIdentity.encoded,
          "x-oopsnote-signature": bootstrapIdentity.signature,
        },
        body: JSON.stringify({
          daily_success_limit: pending.dailySuccessLimit,
          preserve_existing_quota: pending.preserveExistingQuota,
        }),
        cache: "no-store",
      });
      if (!bootstrapResponse.ok) {
        console.error(
          "OopsNote workspace provisioning was rejected by the backend",
          { status: bootstrapResponse.status },
        );
        return Response.json(
          { detail: "工作区初始化失败，后端拒绝了身份或配置。请检查后端认证设置。" },
          { status: 502 },
        );
      }
      markWorkspaceProvisioned(session.user.id);
    } catch (error) {
      console.error("OopsNote initial workspace quota provisioning failed", error);
      return Response.json(
        { detail: "OopsNote 后端未运行，暂时无法初始化工作区。" },
        { status: 503 },
      );
    }
  }
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
