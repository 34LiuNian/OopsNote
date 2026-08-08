import { randomBytes, timingSafeEqual } from "node:crypto";
import type { BetterAuthPlugin } from "better-auth";

const gateCapability = randomBytes(32).toString("base64url");
const gateHeader = "x-oopsnote-admin-gate";
const guardedAdminWrites = new Set([
  "/admin/admin-update-user",
  "/admin/ban-user",
  "/admin/create-user",
  "/admin/impersonate-user",
  "/admin/remove-user",
  "/admin/revoke-user-session",
  "/admin/revoke-user-sessions",
  "/admin/set-role",
  "/admin/set-user-password",
  "/admin/unban-user",
]);

function hasCapability(request: Request): boolean {
  const supplied = request.headers.get(gateHeader) || "";
  const expected = Buffer.from(gateCapability);
  const candidate = Buffer.from(supplied);
  return candidate.length === expected.length && timingSafeEqual(candidate, expected);
}

export function withAdminGate(headers?: HeadersInit): Headers {
  const gated = new Headers(headers);
  gated.set(gateHeader, gateCapability);
  return gated;
}

export const betterAuthAdminGatePlugin: BetterAuthPlugin = {
  id: "oopsnote-admin-gate",
  version: "1.0.0",
  async onRequest(request) {
    const pathname = new URL(request.url).pathname;
    const authPath = pathname.startsWith("/api/auth") ? pathname.slice("/api/auth".length) : pathname;
    if (guardedAdminWrites.has(authPath) && !hasCapability(request)) {
      return { response: Response.json({ message: "Not found" }, { status: 404 }) };
    }
  },
};
