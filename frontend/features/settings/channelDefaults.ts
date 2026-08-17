export const PROVIDER_DEFAULT_URLS: Record<string, string | null> = {
  deepseek: "https://api.deepseek.com/v1",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
  google: "https://generativelanguage.googleapis.com",
  "openai-compatible": null,
};

function normalizedBaseUrl(value: string | null): string | null {
  return value?.trim().replace(/\/+$/, "") || null;
}

export function baseUrlAfterProviderChange(
  currentProvider: string,
  currentBaseUrl: string | null,
  nextProvider: string,
): string | null {
  const currentUrl = normalizedBaseUrl(currentBaseUrl);
  const previousDefault = normalizedBaseUrl(PROVIDER_DEFAULT_URLS[currentProvider] ?? null);
  return currentUrl && currentUrl !== previousDefault
    ? currentBaseUrl
    : PROVIDER_DEFAULT_URLS[nextProvider] ?? null;
}
