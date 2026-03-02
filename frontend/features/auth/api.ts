import { fetchJson } from "../../lib/api";
import type {
  AdminPasswordResetRequest,
  AdminUserUpdateRequest,
  AuthMeResponse,
  AuthTokenResponse,
  LoginRequest,
  PasswordUpdateRequest,
  RegisterRequest,
  RegistrationSettingsResponse,
  RegistrationSettingsUpdateRequest,
  UserListResponse,
  UserProfileUpdateRequest,
} from "../../types/api";

export async function login(payload: LoginRequest): Promise<AuthTokenResponse> {
  return fetchJson<AuthTokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

export async function register(payload: RegisterRequest): Promise<AuthTokenResponse> {
  return fetchJson<AuthTokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

export async function getMe(): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>("/auth/me");
}

export async function getRegistrationEnabled(): Promise<RegistrationSettingsResponse> {
  return fetchJson<RegistrationSettingsResponse>("/auth/registration", {
    skipAuth: true,
  });
}

export async function getRegistrationSettings(): Promise<RegistrationSettingsResponse> {
  return fetchJson<RegistrationSettingsResponse>("/settings/auth-registration");
}

export async function updateRegistrationSettings(
  payload: RegistrationSettingsUpdateRequest
): Promise<RegistrationSettingsResponse> {
  return fetchJson<RegistrationSettingsResponse>("/settings/auth-registration", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getAccountMe(): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>("/account/me");
}

export async function updateAccountMe(
  payload: UserProfileUpdateRequest
): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>("/account/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function updatePassword(
  payload: PasswordUpdateRequest
): Promise<{ message: string }> {
  return fetchJson<{ message: string }>("/account/password", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listUsers(query: string): Promise<UserListResponse> {
  const nextQuery = query.trim();
  const suffix = nextQuery ? `?query=${encodeURIComponent(nextQuery)}` : "";
  return fetchJson<UserListResponse>(`/users${suffix}`);
}

export async function updateUser(
  username: string,
  payload: AdminUserUpdateRequest
): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>(`/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function resetUserPassword(
  username: string,
  payload: AdminPasswordResetRequest
): Promise<AuthMeResponse> {
  return fetchJson<AuthMeResponse>(`/users/${encodeURIComponent(username)}/password`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
