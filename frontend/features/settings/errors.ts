export function formatApiError(err: unknown, fallback: string) {
  if (!(err instanceof Error)) return fallback;
  const text = err.message?.trim();
  if (!text) return fallback;

  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  } catch {
    // ignore JSON parse errors
  }

  return text;
}
