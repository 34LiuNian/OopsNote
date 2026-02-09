"use client";

import { useMemo } from "react";
import { LatexAssetRenderer } from "./LatexAssetRenderer";

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
  const normalized = useMemo(() => normalizeChemfig(code), [code]);
  return (
    <LatexAssetRenderer
      kind="chemfig"
      content={normalized}
      inline={inline}
      loadingLabel="Chemfig 渲染中..."
      errorLabel="Chemfig 渲染失败"
    />
  );
}
