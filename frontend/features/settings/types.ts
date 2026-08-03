export type AiProviderProfile = {
  id: string;
  version: number;
  display_name: string;
  provider: string;
  model: string;
  base_url: string | null;
  enabled: boolean;
  has_secret: boolean;
  is_default: boolean;
  is_ocr: boolean;
  capability: { tool_calling: boolean; vision: boolean };
  created_at: string | null;
  updated_at: string | null;
  secret_updated_at: string | null;
  validation: ProviderValidation | null;
};

export type ProviderValidation = {
  success: boolean;
  provider: string;
  model: string;
  latency_ms: number | null;
  error_code: string | null;
  message: string;
  tested_at: string;
};

export type AiProfilesResponse = { items: AiProviderProfile[] };

export type AiProfileDraft = {
  id: string;
  display_name: string;
  provider: string;
  model: string;
  base_url: string | null;
  enabled: boolean;
  capability: { tool_calling: boolean; vision: boolean };
};
