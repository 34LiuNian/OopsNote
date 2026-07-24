"use client";

import { useEffect, useState } from "react";

const SPLASH_READY_TIMEOUT_MS = 10_000;

export function SplashScreen() {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let onWindowLoad: (() => void) | undefined;

    const windowLoaded = new Promise<void>((resolve) => {
      if (document.readyState === "complete") {
        resolve();
        return;
      }
      onWindowLoad = () => resolve();
      window.addEventListener("load", onWindowLoad, { once: true });
    });

    const fontsReady = document.fonts?.ready.then(() => undefined).catch(() => undefined) ?? Promise.resolve();
    const nextStablePaint = () => new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
    });
    const reveal = () => {
      if (!cancelled) setIsReady(true);
    };

    void Promise.all([windowLoaded, fontsReady]).then(nextStablePaint).then(reveal);
    const fallbackTimer = window.setTimeout(reveal, SPLASH_READY_TIMEOUT_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(fallbackTimer);
      if (onWindowLoad) window.removeEventListener("load", onWindowLoad);
    };
  }, []);

  return (
    <div id="oops-splash" className={isReady ? "is-ready" : undefined} aria-hidden="true">
      <div className="oops-splash__loader">
        <div className="oops-splash__circle" />
        <div className="oops-splash__text">
          <span className="oops-splash__tip">加载中</span>
        </div>
      </div>
      <div className="oops-splash__section oops-splash__section--left" />
      <div className="oops-splash__section oops-splash__section--right" />
    </div>
  );
}
