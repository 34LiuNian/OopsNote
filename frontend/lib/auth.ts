"use client";

type AuthConfig = {
  authority: string;
  clientId: string;
  redirectUri: string;
  postLogoutRedirectUri: string;
  scope: string;
  authorizeEndpoint: string;
  tokenEndpoint: string;
  userInfoEndpoint: string;
  endSessionEndpoint: string;
};

export type AuthUser = {
  subject: string;
  displayName: string;
  email: string | null;
  picture: string | null;
  roles: string[];
};

type SessionRecord = {
  access_token: string;
  expires_at: number;
  user?: AuthUser;
};

const SESSION_KEY = "oopsnote.oidc.session";
const STATE_KEY = "oopsnote.oidc.state";

function required(name: string, value: string | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) throw new Error(`Missing auth configuration: ${name}`);
  return trimmed;
}

export function authConfig(): AuthConfig {
  const authority = required("NEXT_PUBLIC_OIDC_AUTHORITY", process.env.NEXT_PUBLIC_OIDC_AUTHORITY).replace(/\/$/, "");
  return {
    authority,
    clientId: required("NEXT_PUBLIC_OIDC_CLIENT_ID", process.env.NEXT_PUBLIC_OIDC_CLIENT_ID),
    redirectUri: required("NEXT_PUBLIC_OIDC_REDIRECT_URI", process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI),
    postLogoutRedirectUri: required(
      "NEXT_PUBLIC_OIDC_POST_LOGOUT_REDIRECT_URI",
      process.env.NEXT_PUBLIC_OIDC_POST_LOGOUT_REDIRECT_URI,
    ),
    scope: (process.env.NEXT_PUBLIC_OIDC_SCOPE || "openid profile email").trim(),
    authorizeEndpoint: `${authority}/authorize`,
    tokenEndpoint: `${authority}/api/oidc/token`,
    userInfoEndpoint: `${authority}/api/oidc/userinfo`,
    endSessionEndpoint: `${authority}/api/oidc/end-session`,
  };
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = Array.from(new Uint8Array(buffer));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function randomString(length = 48): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => alphabet[value % alphabet.length]).join("");
}

async function pkceChallenge(verifier: string): Promise<string> {
  const encoded = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return base64UrlEncode(digest);
}

function loadSession(): SessionRecord | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as SessionRecord;
    if (!parsed.access_token || !parsed.expires_at) return null;
    if (parsed.expires_at <= Date.now()) {
      window.sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    window.sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

function saveSession(session: SessionRecord): void {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function userFromUserInfo(payload: unknown): AuthUser {
  if (!payload || typeof payload !== "object") throw new Error("OIDC userinfo response is invalid");
  const claims = payload as Record<string, unknown>;
  const subject = optionalString(claims.sub);
  if (!subject) throw new Error("OIDC userinfo response is missing subject");
  const email = optionalString(claims.email);
  const displayName = optionalString(claims.name)
    ?? optionalString(claims.preferred_username)
    ?? email
    ?? subject;
  return {
    subject,
    displayName,
    email,
    picture: optionalString(claims.picture),
    roles: [
      ...(Array.isArray(claims.roles) ? claims.roles.filter((value): value is string => typeof value === "string") : []),
      ...(typeof claims.role === "string" ? [claims.role] : []),
      ...(Array.isArray((claims.realm_access as { roles?: unknown } | undefined)?.roles) ? ((claims.realm_access as { roles: unknown[] }).roles.filter((value): value is string => typeof value === "string")) : []),
    ],
  };
}

export function isAdminUser(user: AuthUser | null): boolean {
  if (!user) return false;
  const configured = (process.env.NEXT_PUBLIC_ADMIN_ROLES || "admin").split(",").map((value) => value.trim()).filter(Boolean);
  return (user.roles ?? []).some((role) => configured.includes(role));
}

async function fetchUserInfo(accessToken: string): Promise<AuthUser> {
  const response = await fetch(authConfig().userInfoEndpoint, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new Error(`OIDC userinfo request failed: ${response.status}`);
  return userFromUserInfo(await response.json());
}

export function clearAuthSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_KEY);
  window.sessionStorage.removeItem(STATE_KEY);
}

export function currentUser(): AuthUser | null {
  return loadSession()?.user ?? null;
}

export async function refreshCurrentUser(): Promise<AuthUser> {
  const session = loadSession();
  if (!session) throw new Error("OIDC session is missing");
  const user = await fetchUserInfo(session.access_token);
  saveSession({ ...session, user });
  return user;
}

export async function beginSignin(returnTo?: string): Promise<never> {
  const config = authConfig();
  const verifier = randomString();
  const state = randomString();
  const challenge = await pkceChallenge(verifier);
  const payload = JSON.stringify({
    state,
    verifier,
    returnTo: returnTo || window.location.pathname || "/",
  });
  window.sessionStorage.setItem(STATE_KEY, payload);
  const url = new URL(config.authorizeEndpoint);
  url.searchParams.set("client_id", config.clientId);
  url.searchParams.set("redirect_uri", config.redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", config.scope);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", state);
  window.location.assign(url.toString());
  throw new Error("Redirecting to sign-in");
}

export async function completeSignin(urlString: string): Promise<string> {
  const config = authConfig();
  const callbackUrl = new URL(urlString);
  const code = callbackUrl.searchParams.get("code");
  const returnedState = callbackUrl.searchParams.get("state");
  if (!code || !returnedState) throw new Error("OIDC callback is missing code or state");
  const rawState = window.sessionStorage.getItem(STATE_KEY);
  if (!rawState) throw new Error("OIDC sign-in state is missing");
  const stored = JSON.parse(rawState) as { state: string; verifier: string; returnTo?: string };
  if (stored.state !== returnedState) throw new Error("OIDC state mismatch");
  const payload = new URLSearchParams();
  payload.set("grant_type", "authorization_code");
  payload.set("client_id", config.clientId);
  payload.set("code", code);
  payload.set("redirect_uri", config.redirectUri);
  payload.set("code_verifier", stored.verifier);
  const response = await fetch(config.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: payload.toString(),
  });
  if (!response.ok) {
    throw new Error(`OIDC token exchange failed: ${response.status}`);
  }
  const token = await response.json() as { access_token: string; expires_in?: number };
  if (!token.access_token) throw new Error("OIDC token response is missing access_token");
  saveSession({
    access_token: token.access_token,
    expires_at: Date.now() + Math.max(60, token.expires_in || 300) * 1000,
  });
  window.sessionStorage.removeItem(STATE_KEY);
  try {
    await refreshCurrentUser();
  } catch (error) {
    console.warn("OIDC sign-in succeeded but userinfo could not be loaded", error);
  }
  return stored.returnTo || "/";
}

export async function accessTokenOrRedirect(): Promise<string> {
  const session = loadSession();
  if (session) return session.access_token;
  return beginSignin(window.location.pathname + window.location.search);
}

export function hasAccessToken(): boolean {
  return Boolean(loadSession());
}

export function beginSignout(): never {
  const config = authConfig();
  clearAuthSession();
  const url = new URL(config.endSessionEndpoint);
  url.searchParams.set("post_logout_redirect_uri", config.postLogoutRedirectUri);
  window.location.assign(url.toString());
  throw new Error("Redirecting to sign-out");
}
