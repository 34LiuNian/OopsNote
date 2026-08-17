"use client";

import { useEffect, useState } from "react";
import { Text } from "@/components/ui/primitives";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";
import { SvgMarkup, type SvgColorMode } from "./SvgMarkup";

type LoadedSvg = {
  url: string;
  markup: string;
  error: string;
};

export function AuthenticatedSvgMarkup({
  path,
  label,
  colorMode = "themed",
  fit = false,
  loadingLabel = "图形准备中…",
}: {
  path: string | null | undefined;
  label: string;
  colorMode?: SvgColorMode;
  fit?: boolean;
  loadingLabel?: string;
}) {
  const assetUrl = useAuthenticatedAssetUrl(path);
  const [loaded, setLoaded] = useState<LoadedSvg>({ url: "", markup: "", error: "" });
  const current = loaded.url === assetUrl ? loaded : null;

  useEffect(() => {
    if (!assetUrl) return;
    const controller = new AbortController();
    void fetch(assetUrl, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`SVG 请求失败：${response.status}`);
        return response.text();
      })
      .then((markup) => setLoaded({ url: assetUrl, markup, error: "" }))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setLoaded({
          url: assetUrl,
          markup: "",
          error: reason instanceof Error ? reason.message : "SVG 请求失败",
        });
      });
    return () => controller.abort();
  }, [assetUrl]);

  if (!path) return null;
  if (!assetUrl || !current) return <Text>{loadingLabel}</Text>;
  if (current.error) return <Text>{current.error}</Text>;
  return <SvgMarkup svg={current.markup} label={label} colorMode={colorMode} fit={fit} />;
}
