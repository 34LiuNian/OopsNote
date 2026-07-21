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
import { MantineProvider } from "@mantine/core";
import { oopsTheme } from "@/theme";

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
  if (typeof window === "undefined") return "light";
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function writePreferenceCookie(value: ThemePreference) {
  if (typeof document === "undefined") return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${STORAGE_KEY}=${encodeURIComponent(value)}; Path=/; Max-Age=${oneYear}; SameSite=Lax`;
}

function applyDocumentColorScheme(resolved: ResolvedTheme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.mantineColorScheme = resolved;
  root.dataset.oopsnoteColorScheme = resolved;
  root.style.colorScheme = resolved;
}

export function ThemeProvider({
  children,
  initialPreference,
}: {
  children: React.ReactNode;
  initialPreference?: ThemePreference;
}) {
  const [preference] = useState<ThemePreference>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(getSystemTheme);

  const mqlRef = useRef<MediaQueryList | null>(null);
  const preferenceRef = useRef<ThemePreference>("system");
  const isInitialMountRef = useRef(true);

  const sync = useCallback(
    (nextPreference: ThemePreference) => {
      const nextResolved = nextPreference === "system" ? getSystemTheme() : nextPreference;
      setResolvedTheme(nextResolved);
      applyDocumentColorScheme(nextResolved);
    },
    [setResolvedTheme]
  );

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    writePreferenceCookie("system");

    preferenceRef.current = "system";
    sync("system");
    isInitialMountRef.current = false;

    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    mqlRef.current = mql;

    const handleChange = () => {
      if (preferenceRef.current !== "system") return;
      const next = getSystemTheme();
      setResolvedTheme(next);
      applyDocumentColorScheme(next);
    };

    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handleChange);
      return () => mql.removeEventListener("change", handleChange);
    }

    mql.addListener(handleChange);
    return () => mql.removeListener(handleChange);
  }, [sync]);

  const setPreference = useCallback(
    (_value: ThemePreference) => {
      preferenceRef.current = "system";
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(STORAGE_KEY);
      }
      writePreferenceCookie("system");
      sync("system");
    },
    [sync]
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, resolvedTheme, setPreference }),
    [preference, resolvedTheme, setPreference]
  );

  return (
    <ThemeContext.Provider value={value}>
      <MantineProvider theme={oopsTheme} forceColorScheme={resolvedTheme} withCssVariables withGlobalClasses>
        {children}
      </MantineProvider>
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
