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
      }
    }

    void render();

    return () => {
      cancelled = true;
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
    <Box sx={{ bg: "canvas.default", overflowX: "auto" }} dangerouslySetInnerHTML={{ __html: svg }} />
  );
}
