import { fetchJson } from "@/lib/api";
import type { ChannelDraft, ChannelsResponse, DiscoveryResult, LangChainPolicy, ProviderChannel, ProviderValidation } from "./types";

type ChannelDiscoveryResponse = {
  channel: ProviderChannel;
  discovery: DiscoveryResult;
  validation: ProviderValidation;
  policy_cleared: boolean;
};

export function getChannels() {
  return fetchJson<ChannelsResponse>("/settings/ai/channels");
}

export function createChannel(payload: ChannelDraft) {
  return fetchJson<{ channel: ProviderChannel }>("/settings/ai/channels", { method: "POST", body: JSON.stringify(payload) });
}

export function updateChannel(channelId: string, payload: Omit<ChannelDraft, "id">) {
  return fetchJson<{ channel: ProviderChannel; policy_cleared: boolean }>(`/settings/ai/channels/${encodeURIComponent(channelId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function updateChannelCredential(channelId: string, secret: string) {
  return fetchJson<ChannelDiscoveryResponse>(`/settings/ai/channels/${encodeURIComponent(channelId)}/credential`, { method: "POST", body: JSON.stringify({ secret }) });
}

export function getChannelCredential(channelId: string) {
  return fetchJson<{ secret: string }>(`/settings/ai/channels/${encodeURIComponent(channelId)}/credential`, {
    cache: "no-store",
  });
}

export function syncChannelModels(channelId: string) {
  return fetchJson<ChannelDiscoveryResponse>(`/settings/ai/channels/${encodeURIComponent(channelId)}/models/sync`, { method: "POST" });
}

export function updateChannelModel(channelId: string, modelId: string, payload: { enabled?: boolean; capability?: { tool_calling: boolean; vision: boolean } }) {
  return fetchJson<{ channel: ProviderChannel; policy_cleared: boolean }>(`/settings/ai/channels/${encodeURIComponent(channelId)}/models/${encodeURIComponent(modelId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function updatePolicy(payload: Omit<LangChainPolicy, "version" | "updated_at">) {
  return fetchJson<{ policy: LangChainPolicy }>("/settings/ai/policy", { method: "PUT", body: JSON.stringify(payload) });
}

export function deleteChannel(channelId: string) {
  return fetchJson<{ deleted: boolean }>(`/settings/ai/channels/${encodeURIComponent(channelId)}`, { method: "DELETE" });
}
