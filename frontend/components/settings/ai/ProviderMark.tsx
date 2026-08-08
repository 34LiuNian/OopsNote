import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { Cable } from "lucide-react";
import { Button, NativeInput } from "@/components/ui/primitives";
import styles from "./aiSettings.module.css";

type ProviderMarkMeta = { label: string; icon?: string; fallback: string };

const PROVIDER_META: Record<string, ProviderMarkMeta> = {
  deepseek: { label: "DeepSeek", icon: "/provider-icons/deepseek-color.svg", fallback: "D" },
  openai: { label: "OpenAI", icon: "/provider-icons/openai-color.svg", fallback: "O" },
  anthropic: { label: "Anthropic", icon: "/provider-icons/anthropic-color.svg", fallback: "A" },
  google: { label: "Google Gemini", icon: "/provider-icons/google-color.svg", fallback: "G" },
  "openai-compatible": { label: "OpenAI Compatible", fallback: "" },
};

type ProviderIcon = { id: string; label: string };

export function providerLabel(provider: string): string {
  return PROVIDER_META[provider]?.label ?? provider;
}

function iconUrl(icon: string | null | undefined): string | undefined {
  return icon && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(icon)
    ? `/provider-icons/${icon}-color.svg`
    : undefined;
}

function markMeta(provider: string, icon: string | null | undefined): ProviderMarkMeta {
  const providerMeta = PROVIDER_META[provider];
  return {
    ...(providerMeta ?? {
      label: provider,
      fallback: provider.trim().slice(0, 1).toUpperCase() || "AI",
    }),
    icon: iconUrl(icon) ?? providerMeta?.icon,
  };
}

export function ProviderMark({ provider, icon, size = 36 }: { provider: string; icon?: string | null; size?: number }) {
  const meta = markMeta(provider, icon);

  return (
    <span
      className={`${styles.providerMark}${meta.icon ? "" : ` ${styles.providerFallback}`}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {meta.icon
        ? <Image src={meta.icon} alt="" width={Math.round(size * 0.68)} height={Math.round(size * 0.68)} />
        : meta.fallback || <Cable size={Math.round(size * 0.48)} strokeWidth={1.8} />}
    </span>
  );
}

export function ProviderIconPicker({
  open,
  provider,
  value,
  onChange,
  onClose,
}: {
  open: boolean;
  provider: string;
  value: string | null;
  onChange: (icon: string | null) => void;
  onClose: () => void;
}) {
  const [icons, setIcons] = useState<ProviderIcon[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    let active = true;
    void fetch("/provider-icons/index.json")
      .then((response) => response.json() as Promise<ProviderIcon[]>)
      .then((items) => { if (active) setIcons(items); })
      .catch(() => { if (active) setIcons([]); });
    return () => { active = false; };
  }, [open]);

  const visibleIcons = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return icons.filter((item) => !normalizedQuery || `${item.id} ${item.label}`.toLocaleLowerCase().includes(normalizedQuery));
  }, [icons, query]);

  if (!open) return null;

  return (
    <div className={styles.providerIconPopover} role="dialog" aria-label="选择供应商图标">
      <div className={styles.providerIconToolbar}>
        <strong>选择图标</strong>
        <NativeInput
          className={styles.providerIconSearch}
          value={query}
          placeholder="搜索图标"
          aria-label="搜索图标"
          onChange={(event) => setQuery(event.currentTarget.value)}
          autoFocus
        />
        <Button type="button" variant="invisible" className={styles.providerIconClose} aria-label="关闭图标选择" onClick={onClose}>×</Button>
      </div>
      <div className={styles.providerIconGrid} role="radiogroup" aria-label="供应商图标素材库">
      <Button
        variant="invisible"
        type="button"
        className={`${styles.providerIconOption}${value === null ? ` ${styles.providerIconOptionSelected}` : ""}`}
        role="radio"
        aria-checked={value === null}
        aria-label="跟随 Provider 默认图标"
        title="跟随 Provider 默认图标"
        onClick={() => { onChange(null); onClose(); }}
      >
        <ProviderMark provider={provider} size={30} />
      </Button>
      {visibleIcons.map((item) => (
        <Button
          variant="invisible"
          type="button"
          key={item.id}
          className={`${styles.providerIconOption}${value === item.id ? ` ${styles.providerIconOptionSelected}` : ""}`}
          role="radio"
          aria-checked={value === item.id}
          aria-label={`使用 ${item.label} 图标`}
          title={item.label}
          onClick={() => { onChange(item.id); onClose(); }}
        >
          <ProviderMark provider={provider} icon={item.id} size={30} />
        </Button>
      ))}
      </div>
      {!visibleIcons.length && <span className={styles.providerIconEmpty}>没有匹配的图标</span>}
    </div>
  );
}
