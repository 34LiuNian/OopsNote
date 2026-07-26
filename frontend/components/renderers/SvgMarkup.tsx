"use client";

import { useEffect, useState } from "react";
import { Box, Text } from "@/components/ui/primitives";

const BLOCKED_ELEMENTS = "script,foreignObject,iframe,object,embed,link,meta,audio,video";
const UNSAFE_CSS = /(?:expression\s*\(|javascript:|vbscript:|data:text\/html|-moz-binding)/i;

export function sanitizeSvgMarkup(markup: string): string {
  if (typeof window === "undefined" || !markup.trim()) return "";

  const parser = new DOMParser();
  const xmlDocument = parser.parseFromString(markup, "image/svg+xml");
  let svg: Element | null =
    !xmlDocument.querySelector("parsererror") && xmlDocument.documentElement.tagName.toLowerCase() === "svg"
      ? xmlDocument.documentElement
      : null;

  // TikZJax can return an HTML wrapper around the generated SVG. Extract only
  // the SVG subtree; surrounding spans and styles are never inserted.
  if (!svg) {
    const htmlDocument = parser.parseFromString(markup, "text/html");
    svg = htmlDocument.querySelector("svg");
  }
  if (!svg) return "";

  svg.querySelectorAll(BLOCKED_ELEMENTS).forEach((element) => element.remove());
  svg.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();

      if (name.startsWith("on")) {
        element.removeAttribute(attribute.name);
        continue;
      }

      if (name === "href" || name === "xlink:href") {
        if (value && !value.startsWith("#") && !value.startsWith("/vendor/tikzjax/")) {
          element.removeAttribute(attribute.name);
        }
        continue;
      }

      if (name === "style" && UNSAFE_CSS.test(value)) {
        element.removeAttribute(attribute.name);
      }
    }

    if (element.tagName.toLowerCase() === "style" && UNSAFE_CSS.test(element.textContent || "")) {
      element.remove();
    }
  });

  return new XMLSerializer().serializeToString(svg);
}

export function SvgMarkup({ svg, label, fit = false }: { svg: string; label?: string; fit?: boolean }) {
  const [result, setResult] = useState<{ source: string; sanitized: string } | null>(null);

  useEffect(() => {
    setResult({ source: svg, sanitized: sanitizeSvgMarkup(svg) });
  }, [svg]);

  if (!result || result.source !== svg) return null;

  if (!result.sanitized) {
    return <Text sx={{ color: "danger.fg", fontSize: 1 }}>SVG 内容无效，无法显示。</Text>;
  }

  return (
    <Box
      role="img"
      aria-label={label}
      sx={{
        width: fit ? "100%" : undefined,
        height: fit ? "100%" : undefined,
        maxWidth: "100%",
        overflow: fit ? "hidden" : undefined,
        overflowX: fit ? undefined : "auto",
        "& svg": {
          display: "block",
          width: fit ? "100%" : undefined,
          maxWidth: "100%",
          height: fit ? "100%" : "auto",
          marginInline: "auto",
        },
      }}
      dangerouslySetInnerHTML={{ __html: result.sanitized }}
    />
  );
}
