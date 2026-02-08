"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Text } from "@primer/react";
import { API_BASE } from "../lib/api";

type ChemfigProps = {
  code: string;
  inline?: boolean;
};

function normalizeChemfig(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return trimmed;
  if (trimmed.includes("\\chemfig")) return trimmed;
  return `\\chemfig{${trimmed}}`;
}

export function Chemfig({ code, inline }: ChemfigProps) {
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [svgText, setSvgText] = useState<string>("");
  const [error, setError] = useState<string>("");

  const normalized = useMemo(() => normalizeChemfig(code), [code]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!normalized) return;
      setStatus("loading");
      setError("");

      try {
        const response = await fetch(`${API_BASE}/latex/chemfig`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            content: normalized,
            inline: Boolean(inline),
          }),
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `请求失败: ${response.status}`);
        }

        const text = await response.text();
        if (cancelled) return;
        setSvgText(text);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setError(err instanceof Error ? err.message : "Chemfig 渲染失败");
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [normalized, inline]);

  if (!normalized) return null;

  if (status === "error") {
    return (
      <Box sx={{ p: 2, border: "1px solid", borderColor: "danger.emphasis", borderRadius: 1, bg: "danger.subtle" }}>
        <Text sx={{ color: "danger.fg", fontSize: 1, whiteSpace: "pre-wrap" }}>{error}</Text>
      </Box>
    );
  }

  if (status !== "ready") {
    return (
      <Box sx={{ p: 2, border: "1px dashed", borderColor: "border.default", borderRadius: 1 }}>
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>Chemfig 渲染中...</Text>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: inline ? "inline-flex" : "block",
        alignItems: "center",
      }}
      dangerouslySetInnerHTML={{ __html: svgText }}
    />
  );
}
