import { NextResponse } from "next/server";
import { bootstrapAdmin, bootstrapSecret } from "@/lib/better-auth-bootstrap";
import { betterAuthIdentityStats } from "@/lib/better-auth-database";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 供登录页/引导页探测：只有运营者挂载了 bootstrap 密钥且尚无用户时才可用。 */
export async function GET() {
  const available = Boolean(bootstrapSecret()) && betterAuthIdentityStats().totalUsers === 0;
  return NextResponse.json({ available });
}

/**
 * 网页引导入口：服务端直接使用已挂载的 bootstrap 密钥，无需调用方携带
 * secret。该端点仅在运营者显式挂载 compose.bootstrap.yml（一次性）时存在，
 * 且创建动作仍然是一次性原子 claim——完成后请立即移除该 override。
 */
export async function POST(request: Request) {
  if (!bootstrapSecret()) {
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
    const message = candidate?.message || "初始化失败";
    const status = Number(candidate?.statusCode || candidate?.status || 500);
    return NextResponse.json({ error: message }, { status: status >= 400 && status < 600 ? status : 500 });
  }
}
