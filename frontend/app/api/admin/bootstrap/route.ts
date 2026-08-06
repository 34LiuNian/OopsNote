import fs from "node:fs";
import { NextResponse } from "next/server";
import { auth, betterAuthIdentityStats } from "@/lib/better-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bootstrapSecret(): string {
  const file = process.env.OOPSNOTE_BOOTSTRAP_SECRET_FILE?.trim();
  if (file) return fs.readFileSync(file, "utf8").trim();
  return process.env.OOPSNOTE_BOOTSTRAP_SECRET?.trim() || "";
}

export async function POST(request: Request) {
  const configured = bootstrapSecret();
  const supplied = request.headers.get("x-oopsnote-bootstrap-secret")?.trim() || "";
  if (!configured || supplied.length < 32 || supplied !== configured) {
    return NextResponse.json({ error: "bootstrap secret 无效" }, { status: 404 });
  }
  const stats = betterAuthIdentityStats();
  if (stats.totalUsers !== 0) {
    return NextResponse.json({ error: "管理员已初始化，bootstrap 已关闭" }, { status: 409 });
  }
  try {
    const body = await request.json() as { email?: unknown; name?: unknown; password?: unknown };
    const email = typeof body.email === "string" ? body.email.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!email || !name || password.length < 12) {
      return NextResponse.json({ error: "email、name 和至少 12 位密码为必填项" }, { status: 400 });
    }
    const result = await auth.api.createUser({
      body: { email, name, password, role: "admin" },
    });
    return NextResponse.json({ user: result.user }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "bootstrap 失败";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
