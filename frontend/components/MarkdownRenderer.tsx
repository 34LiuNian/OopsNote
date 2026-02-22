"use client";

import { Box } from "@primer/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Mermaid } from "./Mermaid";
import { Smiles } from "./Smiles";
import { Chemfig } from "./Chemfig";
import { useEffect, useMemo, useRef } from "react";

export function MarkdownRenderer({ text, fontSize }: { text: string; fontSize?: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const processedText = useMemo(() => {
    if (!text) return "";
    // Handle potential HTML escaping from backend
    let unescaped = text
      .replace(/\\\$/g, "$") // Unescape escaped dollar signs
      .replace(/\\\[\\/g, "\\[") // Unescape escaped brackets
      .replace(/\\\]\\/g, "\\]"); // Unescape escaped brackets
    
    // Convert LaTeX enumerate environments to simple line breaks
    // Remove \begin{enumerate} and \end{enumerate}, keep \item content
    unescaped = unescaped
      .replace(/\\begin\{enumerate\}/g, "")
      .replace(/\\end\{enumerate\}/g, "")
      .replace(/\\item\[(.*?)\]/g, "\n\n$1") // \item[(1)] → \n\n(1)
      .replace(/\\item/g, "\n\n"); // \item → \n\n
    
    // Force displaystyle for inline math markers to match LaTeX output and avoid compression.
    // Handles $...$ and \(...\) while avoiding $$...$$ and \[...\]
    return unescaped
      .replace(/\$(?!\$)([\s\S]*?)\$/g, (match, p1) => {
        if (p1.trim().startsWith("\\displaystyle")) return match;
        return `$\\displaystyle ${p1}$`;
      })
      .replace(/\\\(([\s\S]*?)\\\)/g, (match, p1) => {
        if (p1.trim().startsWith("\\displaystyle")) return match;
        return `\\(\\displaystyle ${p1}\\)`;
      });
  }, [text]);

  useEffect(() => {
    // We ignore TypeScript errors for this dynamic import since katex doesn't have proper types for it
    // @ts-ignore
    void import("katex/contrib/mhchem");
    // Load additional KaTeX extensions that might be needed for array environments
    // @ts-ignore
    void import("katex/dist/contrib/auto-render");
  }, []);

  const remarkPlugins = useMemo(() => {
    return [remarkGfm, remarkMath, remarkBreaks];
  }, []);

  const rehypePlugins = useMemo(() => {
    // Configure rehype-katex with strict: "ignore" to support array, hline, and other advanced LaTeX features
    // Also enable trust for safety since we control the content
    return [[rehypeKatex, { strict: "ignore", trust: true }] as any];
  }, []);

  return (
    <Box ref={containerRef} sx={{ fontSize: fontSize ?? 1, "& .katex": { fontSize: "1.1em" } }}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          p: ({ children }) => (
            <Box as="p" sx={{ m: 0, mb: 2, whiteSpace: "pre-wrap" }}>
              {children}
            </Box>
          ),
          ul: ({ children }) => <Box as="ul" sx={{ pl: 3, mt: 0, mb: 2 }}>{children}</Box>,
          ol: ({ children }) => <Box as="ol" sx={{ pl: 3, mt: 0, mb: 2 }}>{children}</Box>,
          li: ({ children }) => <Box as="li" sx={{ mb: 1, whiteSpace: "pre-wrap" }}>{children}</Box>,
          pre: ({ children }) => {
            const child = Array.isArray(children) ? children[0] : children;
            const className = (child as { props?: { className?: string } })?.props?.className || "";
            const language = className.replace("language-", "").trim();

            if (language === "smiles" || language === "mermaid" || language === "chemfig") {
              return (
                <Box sx={{ m: 0, mb: 2 }}>
                  {children}
                </Box>
              );
            }

            return (
              <Box
                as="pre"
                sx={{
                  whiteSpace: "pre-wrap",
                  fontFamily: "mono",
                  fontSize: 1,
                  m: 0,
                  mb: 2,
                  p: 2,
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "border.default",
                  bg: "canvas.subtle",
                  overflowX: "auto",
                }}
              >
                {children}
              </Box>
            );
          },
          code: ({ className, children }) => {
            const raw = String(children ?? "");
            const language = (className || "").replace("language-", "").trim();

            if (language === "mermaid") {
              return <Mermaid code={raw} />;
            }

            if (language === "smiles") {
              return <Smiles code={raw} />;
            }

            if (language === "chemfig") {
              return <Chemfig code={raw} />;
            }

            return (
              <Box as="code" sx={{ fontFamily: "mono", fontSize: 1, whiteSpace: "pre-wrap" }}>
                {children}
              </Box>
            );
          },
        }}
      >
        {processedText}
      </ReactMarkdown>
    </Box>
  );
}
