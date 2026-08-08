export function isBetterAuthMode(): boolean {
  return (process.env.NEXT_PUBLIC_AUTH_MODE || "oidc").trim().toLowerCase() === "better-auth";
}
