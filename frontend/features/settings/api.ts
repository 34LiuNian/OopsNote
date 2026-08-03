import { fetchJson } from "@/lib/api";
import type { AiProfileDraft, AiProfilesResponse, AiProviderProfile, ProviderValidation } from "./types";

export function getAiProfiles() {
  return fetchJson<AiProfilesResponse>("/settings/ai/profiles");
}

export function createAiProfile(payload: AiProfileDraft) {
  return fetchJson<{ profile: AiProviderProfile }>("/settings/ai/profiles", { method: "POST", body: JSON.stringify(payload) });
}

export function updateAiProfile(profileId: string, payload: Omit<AiProfileDraft, "id">) {
  return fetchJson<{ profile: AiProviderProfile }>(`/settings/ai/profiles/${encodeURIComponent(profileId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function updateAiCredential(profileId: string, secret: string) {
  return fetchJson<{ profile: AiProviderProfile; validation: ProviderValidation }>(`/settings/ai/profiles/${encodeURIComponent(profileId)}/credential`, { method: "POST", body: JSON.stringify({ secret }) });
}

export function deleteAiCredential(profileId: string) {
  return fetchJson<{ profile: AiProviderProfile }>(`/settings/ai/profiles/${encodeURIComponent(profileId)}/credential`, { method: "DELETE" });
}

export function testAiProfile(profileId: string) {
  return fetchJson<{ validation: ProviderValidation }>(`/settings/ai/profiles/${encodeURIComponent(profileId)}/test`, { method: "POST" });
}

export function deleteAiProfile(profileId: string) {
  return fetchJson<{ deleted: boolean }>(`/settings/ai/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
}

export function activateAiProfile(profileId: string) {
  return fetchJson("/settings/ai/default-profile", { method: "PUT", body: JSON.stringify({ profile_id: profileId }) });
}

export function activateOcrProfile(profileId: string) {
  return fetchJson("/settings/ai/ocr-profile", { method: "PUT", body: JSON.stringify({ profile_id: profileId }) });
}
