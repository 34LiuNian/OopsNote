"use client";

import { useEffect, useMemo, useState } from "react";
import type { RDKitModule } from "@rdkit/rdkit";
import { Box, Text } from "@/components/ui/primitives";
import { sanitizeSvgMarkup, SvgMarkup } from "./SvgMarkup";

const RDKIT_SCRIPT = "/vendor/rdkit/RDKit_minimal.js";
const RDKIT_WASM = "/vendor/rdkit/RDKit_minimal.wasm";
const SVG_CACHE = new Map<string, string>();
let rdkitPromise: Promise<RDKitModule> | null = null;

function loadRdkit(): Promise<RDKitModule> {
  if (rdkitPromise) return rdkitPromise;

  rdkitPromise = new Promise<void>((resolve, reject) => {
    const rdkitWindow = window as unknown as { initRDKitModule?: () => Promise<RDKitModule> };
    if (typeof rdkitWindow.initRDKitModule === "function") {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = RDKIT_SCRIPT;
    script.async = true;
    script.dataset.oopsnoteRdkit = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("RDKit 脚本加载失败"));
    document.head.appendChild(script);
  }).then(() => {
    const rdkitWindow = window as unknown as { initRDKitModule?: (options: { locateFile: () => string }) => Promise<RDKitModule> };
    if (typeof rdkitWindow.initRDKitModule !== "function") {
      throw new Error("RDKit 初始化函数不可用");
    }
    return rdkitWindow.initRDKitModule({ locateFile: () => RDKIT_WASM });
  });

  rdkitPromise.catch(() => {
    rdkitPromise = null;
  });
  return rdkitPromise;
}

async function renderMolecule(source: string): Promise<string> {
  const cached = SVG_CACHE.get(source);
  if (cached) return cached;

  const rdkit = await loadRdkit();
  const molecule = rdkit.get_mol(source);
  if (!molecule) throw new Error("无法解析分子结构，请检查 SMILES 或 MolBlock");

  try {
    const svg = molecule.get_svg_with_highlights(
      JSON.stringify({
        width: 520,
        height: 220,
        clearBackground: true,
        useBWAtomPalette: true,
        bondLineWidth: 1.2,
        minFontSize: 10,
        maxFontSize: 24,
        legend: "",
        atoms: [],
        bonds: [],
      }),
    );
    const sanitized = sanitizeSvgMarkup(svg);
    if (!sanitized) throw new Error("RDKit 返回了无效 SVG");
    SVG_CACHE.set(source, sanitized);
    return sanitized;
  } finally {
    molecule.delete();
  }
}

export function MoleculeRenderer({ code }: { code: string }) {
  const source = useMemo(() => code.trim(), [code]);
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setSvg("");
    setError("");
    if (!source) return;

    if (source.length > 50_000) {
      setError("分子结构数据过长，已停止渲染");
      return;
    }

    void renderMolecule(source)
      .then((result) => {
        if (!cancelled) setSvg(result);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "分子结构渲染失败");
      });

    return () => {
      cancelled = true;
    };
  }, [source]);

  if (error) {
    return (
      <Box sx={{ p: 2, border: "1px solid", borderColor: "danger.emphasis", borderRadius: 1, bg: "danger.subtle" }}>
        <Text sx={{ color: "danger.fg", fontSize: 1 }}>{error}</Text>
        <Box as="pre" sx={{ mt: 2, mb: 0, whiteSpace: "pre-wrap", fontFamily: "mono", fontSize: 0 }}>
          {source}
        </Box>
      </Box>
    );
  }

  if (!svg) return <Text sx={{ color: "fg.muted", fontSize: 1 }}>正在加载分子结构...</Text>;
  return <SvgMarkup svg={svg} label="分子结构" />;
}
