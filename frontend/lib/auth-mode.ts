export function isBetterAuthMode(): boolean {
  return (process.env.NEXT_PUBLIC_AUTH_MODE || "better-auth").trim().toLowerCase() === "better-auth";
}

export function isLocalAuthMode(): boolean {
  return (process.env.NEXT_PUBLIC_AUTH_MODE || "better-auth").trim().toLowerCase() === "local";
}
