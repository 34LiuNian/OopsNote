"use client";

import { useEffect, useMemo, useState } from "react";
import { apiErrorFromResponse, fetchApi } from "../lib/api";

type LatexAssetKind = "tikz";

type LatexAssetState = {
  key: string;
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
  tikz: "/latex/tikz",
};

const CACHE = new Map<string, CacheEntry>();

function buildCacheKey(kind: LatexAssetKind, content: string, inline?: boolean): string {
  return `${kind}:${inline ? "1" : "0"}:${content}`;
}

async function requestAsset(kind: LatexAssetKind, content: string, inline?: boolean): Promise<string> {
  const response = await fetchApi(ASSET_ENDPOINTS[kind], {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ source: content }),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  return response.text();
}

export function useLatexAsset(props: { kind: LatexAssetKind; content: string; inline?: boolean }): LatexAssetState {
  const { kind, content, inline } = props;
  const cacheKey = useMemo(() => (content ? buildCacheKey(kind, content, inline) : ""), [kind, content, inline]);
  const [state, setState] = useState<LatexAssetState>({ key: "", status: "idle", data: "", error: "" });

  useEffect(() => {
    if (!content) return;

    let cancelled = false;
    const cached = CACHE.get(cacheKey);

    if (cached?.status === "ready") {
      return;
    }

    if (cached?.status === "error") {
      return;
    }

    let promise = cached?.promise;
    if (!promise) {
      promise = requestAsset(kind, content, inline);
      CACHE.set(cacheKey, { promise });
    }

    promise
      .then((text) => {
        CACHE.set(cacheKey, { status: "ready", data: text });
        if (!cancelled) {
          setState({ key: cacheKey, status: "ready", data: text, error: "" });
        }
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : "渲染失败";
        CACHE.set(cacheKey, { status: "error", error: message });
        if (!cancelled) {
          setState({ key: cacheKey, status: "error", data: "", error: message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey, content, inline, kind]);

  if (!content) return { key: "", status: "idle", data: "", error: "" };

  const cached = CACHE.get(cacheKey);
  if (cached?.status === "ready") {
    return { key: cacheKey, status: "ready", data: cached.data || "", error: "" };
  }
  if (cached?.status === "error") {
    return { key: cacheKey, status: "error", data: "", error: cached.error || "渲染失败" };
  }
  if (state.key === cacheKey) return state;
  return { key: cacheKey, status: "loading", data: "", error: "" };
}
