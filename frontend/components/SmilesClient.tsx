"use client";

import { Box, Text } from "@primer/react";
import { useEffect, useMemo, useRef, useState } from "react";

export function SmilesClient({ code }: { code: string }) {
  const smiles = useMemo(() => (code || "").trim(), [code]);
  const [error, setError] = useState<string>("");
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [debugInfo, setDebugInfo] = useState<string>("");
  const [renderMode, setRenderMode] = useState<"svg" | "none">("none");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const svgId = useMemo(() => `smiles-svg-${Math.random().toString(36).slice(2, 10)}`, []);

  const width = 320;
  const height = 84;

  useEffect(() => {
    let cancelled = false;

    async function render() {
      setError("");
      setDebugInfo("");
      setIsRendering(false);

      if (!smiles) return;

      const svg = svgRef.current;
      if (!svg) return;
      while (svg.firstChild) {
        svg.removeChild(svg.firstChild);
      }
      setRenderMode("none");

      setIsRendering(true);

      try {
        const mod = (await import("smiles-drawer")) as any;
        const SmilesDrawer = mod.default ?? mod;
        const modKeys = Object.keys(mod || {}).sort().join(", ");

        SmilesDrawer.parse(
          smiles,
          (tree: any) => {
            try {
              if (cancelled) return;
              let svgError: string | null = null;

              try {
                const svgDrawer = new SmilesDrawer.SvgDrawer({ width, height });
                svgDrawer.draw(tree, svg, "light", null, false);
                setRenderMode("svg");
                setIsRendering(false);
              } catch (e) {
                svgError = e instanceof Error ? e.message : String(e);
                throw new Error(
                  `SMILES 渲染失败：无法初始化绘图容器${svgError ? ` (svg=${svgError})` : ""}`,
                );
              }

              setIsRendering(false);
            } catch (e) {
              if (cancelled) return;
              const message = e instanceof Error ? e.message : "SMILES 渲染失败";
              setError(message);
              setDebugInfo(
                [
                  `ua=${navigator.userAgent}`,
                  `smiles=${smiles}`,
                  `svgId=${svgId}`,
                  `svg=${Boolean(svgRef.current)}`,
                  `renderMode=${renderMode}`,
                  `moduleKeys=${modKeys || "(none)"}`,
                ].join("\n"),
              );
              setIsRendering(false);
            }
          },
          (err: any) => {
            if (cancelled) return;
            const message = err?.message || "SMILES 解析失败";
            setError(message);
            setDebugInfo(
              [
                `ua=${navigator.userAgent}`,
                `smiles=${smiles}`,
                `svgId=${svgId}`,
                `svg=${Boolean(svgRef.current)}`,
                `renderMode=${renderMode}`,
              ].join("\n"),
            );
            setIsRendering(false);
          },
        );
      } catch (e) {
        if (cancelled) return;
        const message = e instanceof Error ? e.message : "SMILES 渲染失败";
        setError(message);
        setDebugInfo(
          [
            `ua=${navigator.userAgent}`,
            `smiles=${smiles}`,
            `svgId=${svgId}`,
            `svg=${Boolean(svgRef.current)}`,
            `renderMode=${renderMode}`,
          ].join("\n"),
        );
        setIsRendering(false);
      }
    }

    void render();

    return () => {
      cancelled = true;
    };
  }, [smiles]);

  if (error) {
    return (
      <Box sx={{ p: 2, border: "1px solid", borderColor: "border.default", borderRadius: 2, bg: "canvas.subtle" }}>
        <Text sx={{ color: "danger.fg", fontSize: 1 }}>结构式渲染失败：{error}</Text>
        {debugInfo ? (
          <Box as="pre" sx={{ mt: 2, mb: 0, whiteSpace: "pre-wrap", fontFamily: "mono", fontSize: 1 }}>
            {debugInfo}
          </Box>
        ) : null}
        <Box as="pre" sx={{ mt: 2, mb: 0, whiteSpace: "pre-wrap", fontFamily: "mono", fontSize: 1 }}>
          {smiles}
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        bg: "canvas.default",
        overflowX: "auto",
      }}
    >
      {isRendering ? <Text sx={{ color: "fg.muted", fontSize: 1 }}>结构式渲染中…</Text> : null}
      <Box sx={{ mt: isRendering ? 2 : 0 }}>
        <Box
          as="svg"
          ref={svgRef}
          id={svgId}
          width={width}
          height={height}
          sx={{ display: renderMode === "svg" ? "block" : "none", maxWidth: "100%" }}
        />
      </Box>
    </Box>
  );
}
