import type { ChannelModel, LangChainPolicy, ProviderChannel, StageSelection } from "./types";

export type PolicyStage = "vision" | "agent" | "review";

export function flattenModels(channels: ProviderChannel[]) {
  return channels.flatMap((channel) => channel.models.filter((model) => model.enabled).map((model) => ({ channel, model })));
}

export function policyModelUnavailableReason(
  channel: ProviderChannel,
  model: ChannelModel,
  stage: PolicyStage,
): string | null {
  if (!channel.enabled) return "渠道已停用";
  if (!channel.has_secret) return "渠道缺少访问凭据";
  if (!model.enabled) return "模型未启用";
  if (stage === "vision" && !model.capability.vision) return "未启用 Vision 能力";
  if (stage !== "vision" && !model.capability.tool_calling) return "未启用 Tool Calling";
  return null;
}

export function findPolicyModel(
  channels: ProviderChannel[],
  selection: StageSelection,
): { channel: ProviderChannel; model: ChannelModel } | null {
  const channel = channels.find((candidate) => candidate.id === selection.channel_id);
  const model = channel?.models.find((candidate) => candidate.id === selection.model_id);
  return channel && model ? { channel, model } : null;
}

export function updatePolicyStage(
  policy: LangChainPolicy,
  stage: PolicyStage,
  selection: StageSelection,
): LangChainPolicy {
  return { ...policy, [stage]: selection };
}
