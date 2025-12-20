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

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("dark");

  const mqlRef = useRef<MediaQueryList | null>(null);
  const preferenceRef = useRef<ThemePreference>("system");

  const sync = useCallback(
    (nextPreference: ThemePreference) => {
      const nextResolved = nextPreference === "system" ? getSystemTheme() : nextPreference;
      setResolvedTheme(nextResolved);
    },
    [setResolvedTheme]
  );

  useEffect(() => {
    const stored = readStoredPreference();
    setPreferenceState(stored);
    preferenceRef.current = stored;
    sync(stored);

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
