"use client";

import { Box, Text } from "@/components/ui/primitives";
import { useTheme } from "@/components/providers/ThemeProvider";
import { useEffect, useId, useState } from "react";

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
        const mod = (await import("mermaid")) as any;
        const mermaid = mod.default ?? mod;

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: resolvedTheme === "dark" ? "dark" : "default",
        });

        const out = await mermaid.render(renderId, src);
        if (cancelled) return;
        setSvg(out?.svg || "");
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

  if (error) {
    return (
      <Box>
        <Text sx={{ color: "danger.fg", fontSize: 1 }}>流程图渲染失败：{error}</Text>
      </Box>
    );
  }

  if (!svg) {
    return (
      <Box>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>流程图渲染中…</Text>
      </Box>
    );
  }

  return (
    <Box data-mermaid-theme={resolvedTheme} sx={{ bg: "canvas.default", overflowX: "auto", maxWidth: "100%" }}>
      <Box
        sx={{
          "& svg": {
            maxWidth: "100%",
            height: "auto",
          },
        }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </Box>
  );
}
