"use client";

/**
 * A bounded, content-addressed browser cache for SVG derived from OopsMark.
 * OopsMark remains authoritative; cached SVG is always safe to discard.
 */

const CACHE_PREFIX = "oopsnote:derived-svg:";
const CACHE_SCHEMA_VERSION = "v1";
const MAX_ENTRIES = 64;
const MAX_SVG_CHARS = 120_000;

type CacheEntry = {
  schemaVersion: typeof CACHE_SCHEMA_VERSION;
  renderer: string;
  sourceHash: string;
  variant: string;
  svg: string;
  createdAt: number;
};

function cacheKey(renderer: string, variant: string, sourceHash: string): string {
  return `${CACHE_PREFIX}${CACHE_SCHEMA_VERSION}:${renderer}:${variant}:${sourceHash}`;
}

async function sourceHash(source: string): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  try {
    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(source),
    );
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function parseEntry(
  raw: string | null,
  renderer: string,
  variant: string,
  hash: string,
): string | null {
  if (!raw) return null;
  try {
    const entry = JSON.parse(raw) as Partial<CacheEntry>;
    if (
      entry.schemaVersion !== CACHE_SCHEMA_VERSION
      || entry.renderer !== renderer
      || entry.variant !== variant
      || entry.sourceHash !== hash
      || typeof entry.svg !== "string"
      || !entry.svg
    ) {
      return null;
    }
    return entry.svg;
  } catch {
    return null;
  }
}

function evictOldest(store: Storage): void {
  const entries: Array<{ key: string; createdAt: number }> = [];
  for (let index = 0; index < store.length; index += 1) {
    const key = store.key(index);
    if (!key?.startsWith(CACHE_PREFIX)) continue;
    try {
      const entry = JSON.parse(store.getItem(key) || "{}") as Partial<CacheEntry>;
      entries.push({ key, createdAt: typeof entry.createdAt === "number" ? entry.createdAt : 0 });
    } catch {
      store.removeItem(key);
    }
  }
  entries.sort((left, right) => left.createdAt - right.createdAt);
  for (const entry of entries.slice(Math.max(0, MAX_ENTRIES - 1))) {
    store.removeItem(entry.key);
  }
}

export async function loadDerivedSvg(
  renderer: string,
  source: string,
  variant = "default",
): Promise<string | null> {
  const store = storage();
  const hash = await sourceHash(source);
  if (!store || !hash) return null;
  try {
    const key = cacheKey(renderer, variant, hash);
    const svg = parseEntry(store.getItem(key), renderer, variant, hash);
    if (svg) return svg;
    store.removeItem(key);
  } catch {
    // The cache is optional in storage-restricted browser contexts.
  }
  return null;
}

export async function storeDerivedSvg(
  renderer: string,
  source: string,
  svg: string,
  variant = "default",
): Promise<void> {
  if (!svg || svg.length > MAX_SVG_CHARS) return;
  const store = storage();
  const hash = await sourceHash(source);
  if (!store || !hash) return;
  try {
    evictOldest(store);
    const entry: CacheEntry = {
      schemaVersion: CACHE_SCHEMA_VERSION,
      renderer,
      sourceHash: hash,
      variant,
      svg,
      createdAt: Date.now(),
    };
    store.setItem(cacheKey(renderer, variant, hash), JSON.stringify(entry));
  } catch {
    // Derived artifacts are optional. Quota/privacy mode must not block display.
  }
}
