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

export function MarkdownRenderer({ text }: { text: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void import("katex/contrib/mhchem");
  }, []);

  const remarkPlugins = useMemo(() => {
    return [remarkGfm, remarkMath, remarkBreaks];
  }, []);

  const rehypePlugins = useMemo(() => {
    return [[rehypeKatex, { throwOnError: false }]];
  }, []);

  return (
    <Box ref={containerRef} sx={{ fontSize: 1, "& .katex": { fontSize: "1.1em" } }}>
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
        {text}
      </ReactMarkdown>
    </Box>
  );
}
