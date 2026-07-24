"use client";

import { Box } from "@/components/ui/primitives";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/contrib/mhchem";
import katex from "katex";
import { Mermaid } from "./Mermaid";
import { MoleculeRenderer } from "./MoleculeRenderer";
import { TikzRenderer } from "./TikzRenderer";
import { prepareContentForWeb } from "@/lib/content/oopsmark";
import type { ContentFormat } from "@/types/api";
import type { PluggableList } from "unified";
import { useEffect, useMemo, useRef } from "react";

/** Patch KaTeX to inject \displaystyle into inline math, mirroring
 *  RyotaUshio/obsidian-auto-displaystyle-inline-math's approach. */
{
  const original = katex.renderToString;
  if (!("__patched" in (katex as unknown as Record<string, unknown>))) {
    (katex as unknown as Record<string, unknown>).__patched = true;
    katex.renderToString = function patched(
      source: string,
      options?: Parameters<typeof katex.renderToString>[1],
    ): string {
      if (options && options.displayMode === false && !source.startsWith("\\displaystyle")) {
        source = "\\displaystyle " + source;
      }
      return original(source, options);
    };
  }
}

export function MarkdownRenderer({
  text,
  format = "legacy-markdown-latex",
  fontSize,
}: {
  text: string;
  format?: ContentFormat;
  fontSize?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const processedText = useMemo(() => prepareContentForWeb(text, format), [format, text]);

  useEffect(() => {
    if (format !== "legacy-markdown-latex") return;
    // @ts-ignore
    void import("katex/dist/contrib/auto-render");
  }, [format]);

  const remarkPlugins = useMemo(() => {
    const plugins: PluggableList = [remarkGfm, remarkMath, remarkBreaks];
    return plugins;
  }, []);

  const rehypePlugins = useMemo(() => {
    const plugins: PluggableList = [];
    plugins.push([rehypeKatex, { strict: "ignore", trust: format === "legacy-markdown-latex" }]);
    return plugins;
  }, [format]);

  return (
    <Box
      ref={containerRef}
      className="oops-markdown"
      sx={{ fontSize: fontSize ?? 1, "& .katex": { fontSize: "1.1em" } }}
    >
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
            let className = "";
            if (child && typeof child === "object" && "props" in child) {
              const props = child.props;
              if (props && typeof props === "object" && "className" in props) {
                className = String(props.className || "");
              }
            }
            const language = className.replace("language-", "").trim();

            if (["molecule", "smiles", "mermaid", "tikz"].includes(language)) {
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

            if (language === "molecule" || language === "smiles") {
              return <MoleculeRenderer code={raw} />;
            }

            if (language === "tikz") {
              return <TikzRenderer code={raw} />;
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
