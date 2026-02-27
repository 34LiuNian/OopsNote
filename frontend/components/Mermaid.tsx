"use client";

import { Box, Text } from "@primer/react";
import { useEffect, useId, useState } from "react";

export function Mermaid({ code }: { code: string }) {
  const id = useId().replace(/[:]/g, "_");
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

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
          theme: "default",
        });

        const out = await mermaid.render(`mmd-${id}`, src);
        if (cancelled) return;
        setSvg(out?.svg || "");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Mermaid 渲染失败");
        // Clean up any error images that mermaid may have inserted into the DOM
        const errorElements = document.querySelectorAll(`[id^="mmd-"]`);
        errorElements.forEach((el) => el.remove());
      }
    }

    void render();

    return () => {
      cancelled = true;
      // Cleanup on unmount
      const errorElements = document.querySelectorAll(`[id^="mmd-"]`);
      errorElements.forEach((el) => el.remove());
    };
  }, [code, id]);

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
    <Box sx={{ bg: "canvas.default", overflowX: "auto", maxWidth: "100%" }}>
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
