"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Text } from "@/components/ui/primitives";
import { LatexAssetRenderer } from "./LatexAssetRenderer";
import { sanitizeSvgMarkup, SvgMarkup } from "./SvgMarkup";

const RENDER_TIMEOUT_MS = 30_000;
const SVG_CACHE = new Map<string, string>();
const CJK_PATTERN = /[\u3400-\u9fff\uf900-\ufaff]/;
let renderQueue: Promise<void> = Promise.resolve();

function enqueue<T>(task: () => Promise<T>): Promise<T> {
  const result = renderQueue.then(task, task);
  renderQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

function normalizeTikzSource(input: string): string {
  let source = input.trim().replace(/\\documentclass(?:\[[^\]]*\])?\{[^}]+\}/g, "");
  if (source.includes("\\begin{document}")) return source;
  if (!source.includes("\\begin{tikzpicture}") && !source.includes("\\begin{tikzcd}")) {
    source = `\\begin{tikzpicture}\n${source}\n\\end{tikzpicture}`;
  }
  return `\\begin{document}\n${source}\n\\end{document}`;
}

export async function renderTikz(source: string): Promise<string> {
  const cached = SVG_CACHE.get(source);
  if (cached) return cached;

  return enqueue(async () => {
    const secondCached = SVG_CACHE.get(source);
    if (secondCached) return secondCached;

    const svg = await new Promise<string>((resolve, reject) => {
      const worker = new Worker("/vendor/tikzjax/worker.js");
      const finish = (callback: () => void) => {
        clearTimeout(timeoutId);
        worker.terminate();
        callback();
      };
      const timeoutId = setTimeout(
        () => finish(() => reject(new Error("TikZJax 渲染超时"))),
        RENDER_TIMEOUT_MS,
      );

      worker.onmessage = (event: MessageEvent<{ svg?: string; error?: string }>) => {
        if (event.data.svg) {
          finish(() => resolve(event.data.svg || ""));
        } else {
          finish(() => reject(new Error(event.data.error || "TikZJax 渲染失败")));
        }
      };
      worker.onerror = (event) => {
        finish(() => reject(new Error(event.message || "TikZJax Worker 加载失败")));
      };
      worker.postMessage({ source: normalizeTikzSource(source) });
    });
    const sanitized = sanitizeSvgMarkup(svg);
    if (!sanitized) throw new Error("TikZJax 返回了无效 SVG");
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

    if (source.length > 50_000 || CJK_PATTERN.test(source)) {
      return;
    }

    void renderTikz(source)
      .then((result) => {
        if (!cancelled) setResult({ source, svg: result, error: "" });
      })
      .catch((reason) => {
        if (!cancelled) setResult({ source, svg: "", error: reason instanceof Error ? reason.message : "TikZJax 渲染失败" });
      });

    return () => {
      cancelled = true;
    };
  }, [source]);

  const error = source.length > 50_000
    ? "TikZ 源码过长"
    : CJK_PATTERN.test(source)
      ? "含中文的 TikZ 交由后端渲染"
      : result.source === source ? result.error : "";
  const svg = result.source === source ? result.svg : "";

  if (svg) return <SvgMarkup svg={svg} label="TikZ 图形" colorMode="themed" fit={fit} />;
  if (error && allowBackendFallback) {
    return (
      <Box data-tikz-client-error={error}>
        <LatexAssetRenderer
          kind="tikz"
          content={source}
          loadingLabel="客户端不兼容，正在请求后端渲染..."
          errorLabel={error}
          fit={fit}
        />
      </Box>
    );
  }
  if (error) return <Text sx={{ color: "danger.fg", fontSize: 1 }}>{error}</Text>;

  return (
    <Box sx={{ py: 2 }}>
      <Text sx={{ color: "fg.muted", fontSize: 1 }}>正在使用 TikZJax 渲染...</Text>
    </Box>
  );
}
