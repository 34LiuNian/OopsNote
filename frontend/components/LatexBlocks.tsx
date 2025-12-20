"use client";

import { useMemo } from "react";
import { BlockMath } from "react-katex";
import { Box, Text } from "@primer/react";

function normalizeLatex(input: string): string {
  const trimmed = input.trim();
  if (trimmed.startsWith("$$") && trimmed.endsWith("$$")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\[") && trimmed.endsWith("\\]")) {
    return trimmed.slice(2, -2).trim();
  }
  if (trimmed.startsWith("\\(") && trimmed.endsWith("\\)")) {
    return trimmed.slice(2, -2).trim();
  }
  return trimmed;
}

export function LatexBlocks(props: {
  blocks: string[] | undefined;
}) {
  const blocks = useMemo(() => (props.blocks ?? []).filter(Boolean), [props.blocks]);

  if (blocks.length === 0) return null;

  return (
    <Box sx={{ mt: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Text sx={{ fontWeight: 'bold' }}>LaTeX</Text>
      </Box>

      <Box sx={{ mt: 2, display: 'grid', gap: 2 }}>
        {blocks.map((raw, idx) => {
          const expr = normalizeLatex(raw);
          return (
            <Box key={`${idx}-${expr.slice(0, 32)}`}>
              <BlockMath math={expr} />
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
