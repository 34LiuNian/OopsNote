export type AiProviderProfile = {
  id: string;
  version: number;
  provider: string;
  model: string;
  base_url: string;
  enabled: boolean;
  has_secret: boolean;
  active: boolean;
  ocr_active: boolean;
};

export type AiProfilesResponse = { items: AiProviderProfile[] };
