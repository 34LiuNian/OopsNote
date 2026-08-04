"use client";

import { useEffect, useState } from "react";
import { apiErrorFromResponse, fetchApi } from "../lib/api";

type AssetEntry = { url?: string; promise?: Promise<string> };

// Object URLs are shared for the browser session so repeated cards do not
// refetch or revoke a URL that another component is still displaying.
const CACHE = new Map<string, AssetEntry>();

function protectedAssetPath(path: string): string | null {
  if (path.startsWith("/assets/")) return path;
  if (path.startsWith("/api/assets/")) return path.slice("/api".length);
  return null;
}

async function requestAsset(path: string): Promise<string> {
  const response = await fetchApi(path);
  if (!response.ok) throw await apiErrorFromResponse(response);
  return URL.createObjectURL(await response.blob());
}

/** Resolve protected OopsNote assets through the authenticated API boundary. */
export function useAuthenticatedAssetUrl(path: string | null | undefined): string {
  const normalized = path ? protectedAssetPath(path) : null;
  const [state, setState] = useState(() => ({
    path: normalized || "",
    url: (normalized && CACHE.get(normalized)?.url) || "",
  }));

  useEffect(() => {
    if (!normalized) {
      return;
    }
    const cached = CACHE.get(normalized);
    if (cached?.url) {
      return;
    }
    let cancelled = false;
    const promise = cached?.promise ?? requestAsset(normalized);
    CACHE.set(normalized, { promise });
    promise.then((next) => {
      CACHE.set(normalized, { url: next });
      if (!cancelled) setState({ path: normalized, url: next });
    }).catch(() => {
      if (!cancelled) setState({ path: normalized, url: "" });
    });
    return () => {
      cancelled = true;
    };
  }, [normalized]);

  if (!normalized) return path || "";
  return CACHE.get(normalized)?.url || (state.path === normalized ? state.url : "");
}
