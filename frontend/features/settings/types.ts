export type AiProviderProfile = {
  id: string;
  version: number;
  provider: string;
  model: string;
  base_url: string;
  enabled: boolean;
  has_secret: boolean;
};

export type AiProfilesResponse = { items: AiProviderProfile[] };
