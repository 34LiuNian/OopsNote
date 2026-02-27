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
      .replace(/\\\$/g, "$"); // Unescape escaped dollar signs: \$ → $
    
    // Remove trailing backslashes at end of lines (common OCR artifact)
    // Match \ at end of line (before \n or end of string), but not part of LaTeX commands
    unescaped = unescaped.replace(/\\(\s*)(?=\n|$)/g, '');
    
    // Normalize line breaks: ensure \n\n is treated as paragraph separator
    // Replace literal \n\n strings with actual double newlines for Markdown parsing
    unescaped = unescaped.replace(/\\n\\n/g, '\n\n');
    unescaped = unescaped.replace(/\\n/g, '\n');
    
    // Convert LaTeX enumerate environments to simple line breaks
    // Remove \begin{enumerate} and \end{enumerate}, keep \item content
    unescaped = unescaped
      .replace(/\\begin\{enumerate\}/g, "")
      .replace(/\\end\{enumerate\}/g, "")
      .replace(/\\item\[(.*?)\]/g, "\n\n$1") // \item[(1)] → \n\n(1)
      .replace(/\\item/g, "\n\n"); // \item → \n\n
    
    // Convert tabular to array (KaTeX doesn't support tabular) and wrap in math mode
    // KaTeX requires array environment to be in math mode
    unescaped = unescaped
      // First convert tabular to array
      .replace(/\\begin\{tabular\}/g, "\\begin{array}")
      .replace(/\\end\{tabular\}/g, "\\end{array}")
      // Then wrap standalone array environments in display math delimiters ($$...$$)
      .replace(
        /(\\begin\{array\}[\s\S]*?\\end\{array\})/g,
        (match) => {
          const trimmed = match.trim();
          if (trimmed.startsWith("$$") || trimmed.startsWith("\\[") || trimmed.startsWith("\\(")) {
            return match;
          }
          return `$$${match}$$`;
        }
      )
      // Wrap standalone \underline{\hspace{...}} in inline math ($...$)
      .replace(
        /(\\underline\{\\hspace\{[^}]+\}\})/g,
        (match) => {
          // Check if already in math mode (preceded by $ or \()
          return `$${match}$`;
        }
      );
    
    // Protect display math ($$...$$ and \[...\]) from inline math processing
    // Replace with placeholders, process inline math, then restore
    const displayMathBlocks: string[] = [];
    unescaped = unescaped
      .replace(/\$\$([\s\S]*?)\$\$/g, (match, p1) => {
        displayMathBlocks.push(match);
        return `__DISPLAY_MATH_${displayMathBlocks.length - 1}__`;
      })
      .replace(/\\\[([\s\S]*?)\\\]/g, (match, p1) => {
        displayMathBlocks.push(match);
        return `__DISPLAY_MATH_${displayMathBlocks.length - 1}__`;
      });
    
    // Force displaystyle for inline math markers to match LaTeX output and avoid compression.
    // Handles $...$ and \(...\) while avoiding $$...$$ and \[...\]
    unescaped = unescaped
      .replace(/\$(?!\$)([\s\S]*?)\$/g, (match, p1) => {
        if (p1.trim().startsWith("\\displaystyle")) return match;
        return `$\\displaystyle ${p1}$`;
      })
      .replace(/\\\(([\s\S]*?)\\\)/g, (match, p1) => {
        if (p1.trim().startsWith("\\displaystyle")) return match;
        return `\\(\\displaystyle ${p1}\\)`;
      });
    
    // Restore display math blocks
    displayMathBlocks.forEach((block, index) => {
      unescaped = unescaped.replace(`__DISPLAY_MATH_${index}__`, block);
    });
    
    return unescaped;
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
