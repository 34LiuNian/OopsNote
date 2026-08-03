import { fetchJson } from "@/lib/api";
import type { AiProfilesResponse, AiProviderProfile } from "./types";

export function getAiProfiles() {
  return fetchJson<AiProfilesResponse>("/settings/provider-profiles");
}

export function createAiProfile(payload: Record<string, unknown>) {
  return fetchJson<{ profile: AiProviderProfile }>("/settings/provider-profiles", { method: "POST", body: JSON.stringify(payload) });
}

export function rotateAiCredential(profileId: string, payload: { secret: string; provider: string; model: string; base_url: string }) {
  return fetchJson<{ profile: AiProviderProfile }>(`/settings/provider-profiles/${encodeURIComponent(profileId)}/secret`, { method: "POST", body: JSON.stringify(payload) });
}

export function activateAiProfile(profileId: string) {
  return fetchJson(`/settings/provider-profiles/${encodeURIComponent(profileId)}/activate`, { method: "POST" });
}

export function activateOcrProfile(profileId: string) {
  return fetchJson("/settings/ocr-profile", { method: "POST", body: JSON.stringify({ profile_id: profileId }) });
}
