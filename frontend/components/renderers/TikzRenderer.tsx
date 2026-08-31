"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useRenderErrorNotification } from "@/hooks/useRenderErrorNotification";
import { sanitizeSvgMarkup, SvgMarkup } from "./SvgMarkup";
import { apiErrorFromResponse, fetchApi } from "@/lib/api";
import sxStyles from "./TikzRenderer.sx.module.css";

const SVG_CACHE = new Map<string, string>();
let renderQueue: Promise<void> = Promise.resolve();

function enqueue<T>(task: () => Promise<T>): Promise<T> {
  const result = renderQueue.then(task, task);
  renderQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

export async function renderTikz(source: string): Promise<string> {
  const cached = SVG_CACHE.get(source);
  if (cached) return cached;

  return enqueue(async () => {
    const secondCached = SVG_CACHE.get(source);
    if (secondCached) return secondCached;

    const response = await fetchApi("/latex/tikz", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    if (!response.ok) throw await apiErrorFromResponse(response);
    const svg = await response.text();
    const sanitized = sanitizeSvgMarkup(svg);
    if (!sanitized) throw new Error("LaTeX 渲染器返回了无效 SVG");
    SVG_CACHE.set(source, sanitized);
    return sanitized;
  });
}

export function TikzRenderer({
  code,
  allowBackendFallback = true,
  fit = false,
}: {
  code: string;
  allowBackendFallback?: boolean;
  fit?: boolean;
}) {
  const source = useMemo(() => code.trim(), [code]);
  const [result, setResult] = useState<{ source: string; svg: string; error: string }>({ source: "", svg: "", error: "" });

  useEffect(() => {
    let cancelled = false;
    if (!source) return;

    void renderTikz(source)
      .then((result) => {
        if (!cancelled) setResult({ source, svg: result, error: "" });
      })
      .catch((reason) => {
        if (!cancelled) setResult({ source, svg: "", error: reason instanceof Error ? reason.message : "TikZ 渲染失败" });
      });

    return () => {
      cancelled = true;
    };
  }, [source]);

  const error = source.length > 50_000 ? "TikZ 源码过长" : result.source === source ? result.error : "";
  const svg = result.source === source ? result.svg : "";
  useRenderErrorNotification("TikZ 渲染失败", error);

  if (svg) return <SvgMarkup svg={svg} label="TikZ 图形" colorMode="themed" fit={fit} />;
  void allowBackendFallback;
  if (error) {
    return <>
      <ErrorBanner message={error} title="TikZ 渲染失败" />
    </>;
  }

  return (
    <Box className={sxStyles.sx2}>
      <Text className={sxStyles.sx3}>正在请求统一 LaTeX 渲染器...</Text>
    </Box>
  );
}
