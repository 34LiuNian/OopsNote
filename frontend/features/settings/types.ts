export type ProviderCapability = { tool_calling: boolean; vision: boolean };

export type ChannelModel = {
  id: string;
  source: string;
  enabled: boolean;
  capability: ProviderCapability;
  discovered_at: string | null;
};

export type ProviderChannel = {
  id: string;
  version: number;
  display_name: string;
  provider: string;
  base_url: string | null;
  enabled: boolean;
  has_secret: boolean;
  models: ChannelModel[];
  created_at: string | null;
  updated_at: string | null;
  secret_updated_at: string | null;
  policy_stages: string[];
};

export type StageSelection = { channel_id: string; model_id: string };
export type LangChainPolicy = {
  version: number;
  vision: StageSelection;
  agent: StageSelection;
  review: StageSelection;
  updated_at: string | null;
};

export type ChannelsResponse = { items: ProviderChannel[]; policy: LangChainPolicy | null };
export type ChannelDraft = {
  id: string;
  display_name: string;
  provider: string;
  base_url: string | null;
  enabled: boolean;
};

export type DiscoveryResult = { count: number; capabilities_unknown: boolean };
export type ProviderValidation = {
  success: boolean;
  provider: string;
  model: string;
  latency_ms: number | null;
  error_code: string | null;
  message: string;
  tested_at: string;
};
