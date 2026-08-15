"use client";

import { Box } from "@/components/ui/primitives";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/contrib/mhchem";
import { Mermaid } from "./Mermaid";
import { MoleculeRenderer } from "./MoleculeRenderer";
import { TikzRenderer } from "./TikzRenderer";
import { prepareContentForWeb } from "@/lib/content/oopsmark";
import { rehypeInlineDisplaystyle } from "@/lib/rehype-inline-displaystyle";
import type { ContentFormat } from "@/types/api";
import type { PluggableList } from "unified";
import { useEffect, useMemo, useRef } from "react";
import sxStyles from "./MarkdownRenderer.sx.module.css";

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
    const plugins: PluggableList = [
      rehypeInlineDisplaystyle,
      [rehypeKatex, { strict: "ignore", trust: format === "legacy-markdown-latex" }],
    ];
    return plugins;
  }, [format]);

  return (
    <Box
      ref={containerRef}
      className="oops-markdown"
      data-font-size={fontSize ?? 1}
    >
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          p: ({ children }) => (
            <Box as="p" className={sxStyles.sx1}>
              {children}
            </Box>
          ),
          ul: ({ children }) => <Box as="ul" className={sxStyles.sx2}>{children}</Box>,
          ol: ({ children }) => <Box as="ol" className={sxStyles.sx3}>{children}</Box>,
          li: ({ children }) => <Box as="li" className={sxStyles.sx4}>{children}</Box>,
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
                <Box className={sxStyles.sx5}>
                  {children}
                </Box>
              );
            }

            return (
              <Box
                as="pre"
                className={sxStyles.sx6}
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
              <Box as="code" className={sxStyles.sx7}>
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
