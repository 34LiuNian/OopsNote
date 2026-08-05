import type { ProviderChannel } from "./types";

export function flattenModels(channels: ProviderChannel[]) {
  return channels.flatMap((channel) => channel.models.filter((model) => model.enabled).map((model) => ({ channel, model })));
}
