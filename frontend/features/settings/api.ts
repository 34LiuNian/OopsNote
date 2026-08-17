import { fetchJson } from "@/lib/api";
import type { ChannelDraft, ChannelsResponse, DiscoveryResult, LangChainPolicy, ProviderCapability, ProviderChannel, ProviderValidation } from "./types";

type ChannelDiscoveryResponse = {
  channel: ProviderChannel;
  discovery: DiscoveryResult;
  validation: ProviderValidation;
};

export type AiRuntimeSettings = { max_concurrency: number };

export function getAiRuntimeSettings() {
  return fetchJson<AiRuntimeSettings>("/settings/ai/runtime");
}

export function updateAiRuntimeSettings(maxConcurrency: number) {
  return fetchJson<AiRuntimeSettings>("/settings/ai/runtime", {
    method: "PUT",
    body: JSON.stringify({ max_concurrency: maxConcurrency }),
  });
}

export function getChannels() {
  return fetchJson<ChannelsResponse>("/settings/ai/channels");
}

export function createChannel(payload: ChannelDraft) {
  return fetchJson<{ channel: ProviderChannel }>("/settings/ai/channels", { method: "POST", body: JSON.stringify(payload) });
}

export function updateChannel(channelId: string, payload: Partial<Omit<ChannelDraft, "id">>) {
  return fetchJson<{ channel: ProviderChannel }>(`/settings/ai/channels/${encodeURIComponent(channelId)}`, { method: "PATCH", body: JSON.stringify(payload) });
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

export function checkChannel(channelId: string, modelId: string) {
  return fetchJson<{ validation: ProviderValidation }>(`/settings/ai/channels/${encodeURIComponent(channelId)}/check`, { method: "POST", body: JSON.stringify({ model_id: modelId }) });
}

export function reorderChannels(channelIds: string[]) {
  return fetchJson<{ items: ProviderChannel[] }>("/settings/ai/channels/order", { method: "PATCH", body: JSON.stringify({ channel_ids: channelIds }) });
}

export function updateChannelModel(channelId: string, modelId: string, payload: { enabled?: boolean; capability?: ProviderCapability }) {
  return fetchJson<{ channel: ProviderChannel }>(`/settings/ai/channels/${encodeURIComponent(channelId)}/models/${encodeURIComponent(modelId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function updatePolicy(payload: Omit<LangChainPolicy, "version" | "updated_at">) {
  return fetchJson<{ policy: LangChainPolicy }>("/settings/ai/policy", { method: "PUT", body: JSON.stringify(payload) });
}

export function deleteChannel(channelId: string) {
  return fetchJson<{ deleted: boolean }>(`/settings/ai/channels/${encodeURIComponent(channelId)}`, { method: "DELETE" });
}
