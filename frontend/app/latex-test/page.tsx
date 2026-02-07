"use client";

import { useCallback, useEffect, useState } from "react";
import { Box, Button, Text, Textarea } from "@primer/react";
import { API_BASE } from "@/lib/api";

const DEFAULT_TEXT = `\\section{引言}
这是一个 LaTeX 论文版式测试页，支持公式、表格、图片等。

\\section{公式}
行内公式：$E=mc^2$。

块级公式：
\\[
\\int_{-\\infty}^{\\infty} e^{-x^2} \\, dx = \\sqrt{\\pi}
\\]

多行：
\\[
\\begin{aligned}
(a+b)^2 &= a^2 + 2ab + b^2 \\
(a-b)^2 &= a^2 - 2ab + b^2
\\end{aligned}
\\]
`;

export default function LatexTestPage() {
  const [input, setInput] = useState(DEFAULT_TEXT);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleCompile = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/latex/compile`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          content: input,
        }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `编译失败: ${response.status}`);
      }

      const blob = await response.blob();
      const nextUrl = URL.createObjectURL(blob);
      setPdfUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return nextUrl;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "编译失败，请检查 LaTeX 内容。");
    } finally {
      setIsLoading(false);
    }
  }, [input]);

  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  return (
    <Box className="no-katex" sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 2 }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Text sx={{ fontSize: 3, fontWeight: "bold" }}>LaTeX 论文版式测试</Text>
          <Text sx={{ fontSize: 1, color: "fg.muted" }}>使用后端 xelatex 编译，结果为 PDF 预览。</Text>
        </Box>
        <Button variant="primary" onClick={handleCompile} disabled={isLoading}>
          {isLoading ? "编译中..." : "编译"}
        </Button>
      </Box>

      {error ? (
        <Box sx={{ border: "1px solid", borderColor: "danger.emphasis", borderRadius: 6, p: 3, bg: "danger.subtle" }}>
          <Text sx={{ color: "danger.fg", fontSize: 1, whiteSpace: "pre-wrap" }}>{error}</Text>
        </Box>
      ) : null}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: ["1fr", "1fr 1fr"],
          gap: 4,
          alignItems: "stretch",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, minHeight: 0 }}>
          <Text sx={{ fontSize: 1, color: "fg.muted" }}>编辑区</Text>
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            sx={{
              flex: 1,
              minHeight: 360,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
              fontSize: 1,
            }}
          />
        </Box>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, minHeight: 0 }}>
          <Text sx={{ fontSize: 1, color: "fg.muted" }}>预览区（A4 PDF）</Text>
          <Box
            sx={{
              flex: 1,
              minHeight: 360,
              overflow: "auto",
              bg: "canvas.subtle",
              border: "1px solid",
              borderColor: "border.default",
              borderRadius: 6,
              p: 3,
              display: "flex",
              justifyContent: "center",
              alignItems: "flex-start",
            }}
          >
            <Box
              sx={{
                width: ["100%", "210mm"],
                height: ["70vh", "297mm"],
                bg: "canvas.default",
                border: "1px solid",
                borderColor: "border.default",
                borderRadius: 6,
                boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
                overflow: "hidden",
              }}
            >
              {pdfUrl ? (
                <iframe title="LaTeX PDF 预览" src={pdfUrl} style={{ width: "100%", height: "100%", border: 0 }} />
              ) : (
                <Box sx={{ p: 4 }}>
                  <Text sx={{ color: "fg.muted" }}>点击“编译”生成 PDF 预览。</Text>
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
