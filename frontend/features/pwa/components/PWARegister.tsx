"use client";

import { useEffect } from "react";

export function PWARegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }

    const register = async () => {
      try {
        const registration = await navigator.serviceWorker.register("/sw.js", {
          scope: "/",
        });
        registration.update().catch(() => undefined);
      } catch {
        // Ignore registration errors in unsupported or restricted contexts.
      }
    };

    void register();
  }, []);

  return null;
}