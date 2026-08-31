import { NextResponse } from "next/server";
import { bootstrapAdmin, bootstrapSecret } from "@/lib/better-auth-bootstrap";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * curl 兼容入口：调用方必须携带与服务器一致的 x-oopsnote-bootstrap-secret。
 * 网页引导请使用 /api/admin/setup（服务端直接读取已挂载的 bootstrap 密钥，
 * 仅在尚无任何用户时可用）。
 */
export async function POST(request: Request) {
  const configured = bootstrapSecret();
  const supplied = request.headers.get("x-oopsnote-bootstrap-secret")?.trim() || "";
  if (!configured || supplied.length < 32 || supplied !== configured) {
    return NextResponse.json({ error: "bootstrap secret 无效" }, { status: 404 });
  }
  try {
    const body = (await request.json()) as { email?: unknown; name?: unknown; password?: unknown };
    const result = await bootstrapAdmin({
      email: typeof body.email === "string" ? body.email : "",
      name: typeof body.name === "string" ? body.name : "",
      password: typeof body.password === "string" ? body.password : "",
    });
    return NextResponse.json({ user: { id: result.userId } }, { status: 201 });
  } catch (error) {
    const candidate = error as { message?: string; status?: number; statusCode?: number } | null;
    const message = candidate?.message || "bootstrap 失败";
    const status = Number(candidate?.statusCode || candidate?.status || 500);
    return NextResponse.json({ error: message }, { status: status >= 400 && status < 600 ? status : 500 });
  }
}
