import Image from "next/image";
import styles from "./aiSettings.module.css";

const PROVIDER_META: Record<string, { label: string; icon?: string; fallback: string }> = {
  deepseek: { label: "DeepSeek", icon: "/provider-icons/deepseek.svg", fallback: "D" },
  openai: { label: "OpenAI", icon: "/provider-icons/openai.svg", fallback: "O" },
  anthropic: { label: "Anthropic", icon: "/provider-icons/anthropic.svg", fallback: "A" },
  google: { label: "Google Gemini", icon: "/provider-icons/google.svg", fallback: "G" },
  "openai-compatible": { label: "OpenAI Compatible", fallback: "C" },
};

export function providerLabel(provider: string): string {
  return PROVIDER_META[provider]?.label ?? provider;
}

export function ProviderMark({ provider, size = 36 }: { provider: string; size?: number }) {
  const meta = PROVIDER_META[provider] ?? {
    label: provider,
    fallback: provider.trim().slice(0, 1).toUpperCase() || "AI",
  };

  return (
    <span
      className={`${styles.providerMark}${meta.icon ? "" : ` ${styles.providerFallback}`}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {meta.icon ? <Image src={meta.icon} alt="" width={Math.round(size * 0.68)} height={Math.round(size * 0.68)} /> : meta.fallback}
    </span>
  );
}
