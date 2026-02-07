"use client";

import { useState } from "react";
import { Box, Button, Heading, Text, Textarea } from "@primer/react";
import { MarkdownRenderer } from "../../components/MarkdownRenderer";

const DEFAULT_TEXT = [
  "# Markdown 题面展示测试",
  "",
  "这是一段普通文本，包含 **加粗**、*斜体*，以及行内公式 $a^2 + b^2 = c^2$。",
  "",
  "## 题干",
  "给定直角三角形，已知 $a=3, b=4$，求 $c$。",
  "",
  "## 选项",
  "- A. 5",
  "- B. 6",
  "- C. 7",
  "- D. 8",
  "",
  "## 公式块",
  "$$\\frac{1}{2}mv^2 = mgh$$",
  "",
  "## 代码块（mermaid）",
  "```mermaid",
  "flowchart LR",
  "  A[输入题图] --> B[OCR/重建]",
  "  B --> C[解题]",
  "  C --> D[打标]",
  "```",
  "",
  "## 代码块（smiles）",
  "```smiles",
  "C1=CC=CC=C1",
  "```",
  "",
  "## 普通代码块",
  "```text",
  "Answer: 5",
  "Reason: 3^2 + 4^2 = 5^2",
  "```",
  "",
  "## 解析",
  "因为 $3^2 + 4^2 = 9 + 16 = 25$，所以 $c=5$。",
].join("\n");

export default function MarkdownTestPage() {
  const [text, setText] = useState(DEFAULT_TEXT);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box>
        <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Markdown</Text>
        <Heading as="h2" sx={{ fontSize: 3 }}>题面渲染测试</Heading>
        <Text sx={{ color: "fg.muted", mt: 1 }}>
          在左侧编辑 Markdown，右侧实时预览渲染效果。
        </Text>
      </Box>

      <Box sx={{ display: "flex", gap: 2 }}>
        <Button size="small" onClick={() => setText(DEFAULT_TEXT)}>恢复默认示例</Button>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: ["1fr", "1fr 1fr"],
          gap: 3,
          alignItems: "stretch",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2 }}>输入</Heading>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={24}
            block
          />
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2 }}>预览</Heading>
          <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
            <MarkdownRenderer text={text} />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
