"use client";

import { Box, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useRenderErrorNotification } from "@/hooks/useRenderErrorNotification";
import { useTheme } from "@/components/providers/ThemeProvider";
import { loadDerivedSvg, storeDerivedSvg } from "@/lib/derived-svg-cache";
import { useEffect, useId, useState } from "react";
import { sanitizeSvgMarkup } from "./SvgMarkup";
import sxStyles from "./Mermaid.sx.module.css";

const RENDERER_VERSION = "mermaid-10.9.3";

export function Mermaid({ code }: { code: string }) {
  const id = useId().replace(/[:]/g, "_");
  const { resolvedTheme } = useTheme();
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const renderPrefix = `mmd-${id}`;
    const renderId = `${renderPrefix}-${resolvedTheme}`;

    function cleanOwnArtifacts() {
      document.querySelectorAll<HTMLElement>('[id^="mmd-"]').forEach((element) => {
        if (element.id.startsWith(renderPrefix)) element.remove();
      });
    }

    async function render() {
      setError("");
      setSvg("");

      const src = (code || "").trim();
      if (!src) return;

      try {
        const cached = await loadDerivedSvg(RENDERER_VERSION, src, resolvedTheme);
        if (cached) {
          if (!cancelled) setSvg(cached);
          return;
        }
        const mod = (await import("mermaid")) as any;
        const mermaid = mod.default ?? mod;

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: resolvedTheme === "dark" ? "dark" : "default",
        });

        const out = await mermaid.render(renderId, src);
        if (cancelled) return;
        const rendered = sanitizeSvgMarkup(out?.svg || "");
        if (!rendered) throw new Error("Mermaid 返回了无效 SVG");
        void storeDerivedSvg(RENDERER_VERSION, src, rendered, resolvedTheme);
        setSvg(rendered);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Mermaid 渲染失败");
        // Clean up any error images that mermaid may have inserted into the DOM
        cleanOwnArtifacts();
      }
    }

    void render();

    return () => {
      cancelled = true;
      // Cleanup on unmount
      cleanOwnArtifacts();
    };
  }, [code, id, resolvedTheme]);

  useRenderErrorNotification("流程图渲染失败", error);

  if (error) {
    return (
      <Box>
        <ErrorBanner message={error} title="流程图渲染失败" />
      </Box>
    );
  }

  if (!svg) {
    return (
      <Box>
        <Text className={sxStyles.sx2}>流程图渲染中…</Text>
      </Box>
    );
  }

  return (
    <Box data-mermaid-theme={resolvedTheme} className={sxStyles.sx3}>
      <Box
        className={sxStyles.sx4}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </Box>
  );
}
