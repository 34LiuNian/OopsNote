"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ThemeProvider as PrimerThemeProvider, BaseStyles } from "@primer/react";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "oopsnote-theme";

type ThemeContextValue = {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (value: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function readStoredPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

function readCookiePreference(): ThemePreference {
  if (typeof document === "undefined") return "system";
  const m = document.cookie.match(
    /(?:^|;\s*)oopsnote-theme=([^;]*)/
  );
  const raw = m ? decodeURIComponent(m[1]) : null;
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

function writePreferenceCookie(value: ThemePreference) {
  if (typeof document === "undefined") return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${STORAGE_KEY}=${encodeURIComponent(value)}; Path=/; Max-Age=${oneYear}; SameSite=Lax`;
}

function applyDocumentColorScheme(resolved: ResolvedTheme) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.oopsnoteColorScheme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function ThemeProvider({
  children,
  initialPreference,
}: {
  children: React.ReactNode;
  initialPreference?: ThemePreference;
}) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => initialPreference ?? "system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("dark");

  const mqlRef = useRef<MediaQueryList | null>(null);
  const preferenceRef = useRef<ThemePreference>("system");

  const sync = useCallback(
    (nextPreference: ThemePreference) => {
      const nextResolved = nextPreference === "system" ? getSystemTheme() : nextPreference;
      setResolvedTheme(nextResolved);
      applyDocumentColorScheme(nextResolved);
    },
    [setResolvedTheme]
  );

  useEffect(() => {
    const stored = readStoredPreference();
    const cookiePref = readCookiePreference();
    const effective = stored !== "system" ? stored : cookiePref;
    setPreferenceState(effective);
    preferenceRef.current = effective;
    sync(effective);

    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    mqlRef.current = mql;

    const handleChange = () => {
      if (preferenceRef.current !== "system") return;
      const next = getSystemTheme();
      setResolvedTheme(next);
    };

    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handleChange);
      return () => mql.removeEventListener("change", handleChange);
    }

    mql.addListener(handleChange);
    return () => mql.removeListener(handleChange);
  }, [sync]);

  const setPreference = useCallback(
    (value: ThemePreference) => {
      setPreferenceState(value);
      preferenceRef.current = value;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, value);
      }
      writePreferenceCookie(value);
      sync(value);
    },
    [sync]
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, resolvedTheme, setPreference }),
    [preference, resolvedTheme, setPreference]
  );

  const primerColorMode = preference === "system" ? "auto" : (preference === "light" ? "day" : "night");

  return (
    <ThemeContext.Provider value={value}>
      <PrimerThemeProvider colorMode={primerColorMode} preventSSRMismatch>
        <BaseStyles style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          {children}
        </BaseStyles>
      </PrimerThemeProvider>
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
