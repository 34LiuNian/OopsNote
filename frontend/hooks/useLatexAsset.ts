"use client";

import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "../lib/api";

type LatexAssetKind = "chemfig" | "tikz";

type LatexAssetState = {
  status: "idle" | "loading" | "ready" | "error";
  data: string;
  error: string;
};

type CacheEntry = {
  status?: "ready" | "error";
  data?: string;
  error?: string;
  promise?: Promise<string>;
};

const ASSET_ENDPOINTS: Record<LatexAssetKind, string> = {
  chemfig: "/latex/chemfig",
  tikz: "/latex/tikz",
};

const CACHE = new Map<string, CacheEntry>();

function buildCacheKey(kind: LatexAssetKind, content: string, inline?: boolean): string {
  return `${kind}:${inline ? "1" : "0"}:${content}`;
}

async function requestAsset(kind: LatexAssetKind, content: string, inline?: boolean): Promise<string> {
  const response = await fetch(`${API_BASE}${ASSET_ENDPOINTS[kind]}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      content,
      inline: Boolean(inline),
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败: ${response.status}`);
  }

  return response.text();
}

export function useLatexAsset(props: { kind: LatexAssetKind; content: string; inline?: boolean }): LatexAssetState {
  const { kind, content, inline } = props;
  const cacheKey = useMemo(() => (content ? buildCacheKey(kind, content, inline) : ""), [kind, content, inline]);
  const [state, setState] = useState<LatexAssetState>({ status: "idle", data: "", error: "" });

  useEffect(() => {
    if (!content) {
      setState({ status: "idle", data: "", error: "" });
      return;
    }

    let cancelled = false;
    const cached = CACHE.get(cacheKey);

    if (cached?.status === "ready") {
      setState({ status: "ready", data: cached.data || "", error: "" });
      return;
    }

    if (cached?.status === "error") {
      setState({ status: "error", data: "", error: cached.error || "渲染失败" });
      return;
    }

    let promise = cached?.promise;
    if (!promise) {
      promise = requestAsset(kind, content, inline);
      CACHE.set(cacheKey, { promise });
    }

    setState({ status: "loading", data: "", error: "" });

    promise
      .then((text) => {
        CACHE.set(cacheKey, { status: "ready", data: text });
        if (!cancelled) {
          setState({ status: "ready", data: text, error: "" });
        }
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : "渲染失败";
        CACHE.set(cacheKey, { status: "error", error: message });
        if (!cancelled) {
          setState({ status: "error", data: "", error: message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, content, inline, kind]);

  return state;
}
