"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

type RenderMathInElement = (
  element: HTMLElement,
  options?: {
    delimiters?: Array<{ left: string; right: string; display: boolean }>;
    ignoredTags?: string[];
    ignoredClasses?: string[];
    errorCallback?: (msg: string, err: unknown) => void;
    macros?: Record<string, string>;
    throwOnError?: boolean;
    strict?: boolean | "warn" | "ignore";
    trust?: boolean | ((context: unknown) => boolean);
    output?: "html" | "mathml" | "htmlAndMathml";
    preProcess?: (math: string) => string;
  },
) => void;

export function KatexAutoRender() {
  const pathname = usePathname();

  useEffect(() => {
    let cancelled = false;
    const timers: Array<ReturnType<typeof setTimeout>> = [];

    async function run() {
      if (typeof document === "undefined") return;

      const mod = (await import("katex/contrib/auto-render")) as unknown as {
        default: RenderMathInElement;
      };

      if (cancelled) return;

      const render = () => {
        if (cancelled) return;
        mod.default(document.body, {
          // Treat common inline delimiters as inline, but inject \inline => \displaystyle
          // to make them render with displaystyle while keeping inline layout.
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "\\[", right: "\\]", display: true },
            { left: "\\(", right: "\\)", display: false },
            { left: "$", right: "$", display: false },
          ],
          ignoredTags: [
            "script",
            "noscript",
            "style",
            "textarea",
            "pre",
            "code",
            "option",
          ],
          ignoredClasses: ["no-katex", "katex", "katex-display"],
          macros: {
            "\\inline": "\\displaystyle",
          },
          preProcess: (math) => `\\inline ${math}`,
          throwOnError: false,
        });
      };

      // DOM may update after route change due to async data fetch.
      queueMicrotask(render);
      timers.push(setTimeout(render, 200));
      timers.push(setTimeout(render, 800));
      timers.push(setTimeout(render, 2000));
      timers.push(setTimeout(render, 3500));
    }

    void run();

    return () => {
      cancelled = true;
      for (const t of timers) clearTimeout(t);
    };
  }, [pathname]);

  return null;
}
