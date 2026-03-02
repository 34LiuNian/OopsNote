import { fetchJson } from "../../lib/api";
import type { AuthMeResponse, AuthTokenResponse, LoginRequest } from "../../types/api";

export async function login(payload: LoginRequest): Promise<AuthTokenResponse> {
  return fetchJson<AuthTokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

export async function getMe(): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>("/auth/me");
}
