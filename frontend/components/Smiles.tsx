"use client";

import { Box, Text } from "@primer/react";
import dynamic from "next/dynamic";

const SmilesClient = dynamic(() => import("./SmilesClient").then((m) => m.SmilesClient), {
  ssr: false,
  loading: () => (
    <Box sx={{ p: 2, border: "1px solid", borderColor: "border.default", borderRadius: 2, bg: "canvas.subtle" }}>
      <Text sx={{ color: "fg.muted", fontSize: 1 }}>结构式渲染中…</Text>
    </Box>
  ),
});

export function Smiles({ code }: { code: string }) {
  return <SmilesClient code={code} />;
}
