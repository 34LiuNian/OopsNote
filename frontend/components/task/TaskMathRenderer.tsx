"use client";

import { useCallback, useEffect, useRef } from "react";
import { Box, Spinner, Text } from "@primer/react";
import type { TaskResponse } from "@/types/api";

interface TaskMathRendererProps {
  data: TaskResponse | null;
}

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

export function TaskMathRenderer({ data }: TaskMathRendererProps) {
  const mathContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!data) return;
    if (!mathContainerRef.current) return;

    let cancelled = false;
    const handle = window.setTimeout(async () => {
      try {
        const mod = (await import("katex/contrib/auto-render")) as unknown as {
          default: RenderMathInElement;
        };
        if (cancelled) return;
        mod.default(mathContainerRef.current as HTMLElement, {
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
      } catch {
        // best-effort
      }
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [data]);

  return <div ref={mathContainerRef} style={{ display: "none" }} />;
}
