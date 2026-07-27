"use client";

import { useEffect, useState } from "react";
import { Box, Text } from "@/components/ui/primitives";

const BLOCKED_ELEMENTS = "script,foreignObject,iframe,object,embed,link,meta,audio,video";
const UNSAFE_CSS = /(?:expression\s*\(|javascript:|vbscript:|data:text\/html|-moz-binding)/i;
const THEMED_COLOR_ATTRIBUTES = new Set(["color", "fill", "flood-color", "lighting-color", "stop-color", "stroke"]);
const CSS_COLOR_DECLARATION = /(^|[;{])(\s*(?:color|fill|flood-color|lighting-color|stop-color|stroke)\s*:\s*)(#[0-9a-f]{3,6}\b|[a-z]+\b|rgba?\([^)]*\))(?=\s*(?:!important)?\s*(?:[;}\n]|$))/gim;

export type SvgColorMode = "preserve" | "themed";

function themedColor(value: string): string | null {
  const compact = value.trim().toLowerCase().replace(/\s+/g, "");
  if (/^(?:#000|#000000|black|rgb\(0,0,0\)|rgba\(0,0,0,1(?:\.0*)?\))$/.test(compact)) {
    return "currentColor";
  }
  if (/^(?:#fff|#ffffff|white|rgb\(255,255,255\)|rgba\(255,255,255,1(?:\.0*)?\))$/.test(compact)) {
    return "var(--oops-svg-background)";
  }
  return null;
}

function themeCssColors(css: string): string {
  return css.replace(CSS_COLOR_DECLARATION, (match, boundary: string, declaration: string, value: string) => {
    const replacement = themedColor(value);
    return replacement ? `${boundary}${declaration}${replacement}` : match;
  });
}

export function sanitizeSvgMarkup(markup: string, colorMode: SvgColorMode = "preserve"): string {
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
  [svg, ...Array.from(svg.querySelectorAll("*"))].forEach((element) => {
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
        continue;
      }

      if (colorMode === "themed" && THEMED_COLOR_ATTRIBUTES.has(name)) {
        const replacement = themedColor(value);
        if (replacement) element.setAttribute(attribute.name, replacement);
      } else if (colorMode === "themed" && name === "style") {
        element.setAttribute(attribute.name, themeCssColors(value));
      }
    }

    if (element.tagName.toLowerCase() === "style") {
      const css = element.textContent || "";
      if (UNSAFE_CSS.test(css)) {
        element.remove();
      } else if (colorMode === "themed") {
        element.textContent = themeCssColors(css);
      }
    }
  });

  return new XMLSerializer().serializeToString(svg);
}

export function SvgMarkup({
  svg,
  label,
  colorMode,
  fit = false,
}: {
  svg: string;
  label?: string;
  colorMode: SvgColorMode;
  fit?: boolean;
}) {
  const preparationKey = `${colorMode}\0${svg}`;
  const [prepared, setPrepared] = useState<{ key: string; markup: string } | null>(null);
  const currentMarkup = prepared?.key === preparationKey ? prepared.markup : null;

  // DOMParser is intentionally browser-owned. Preparing after hydration keeps
  // the server and first client render identical instead of rendering an error
  // on the server and replacing it with SVG during hydration.
  useEffect(() => {
    const preparationTimer = window.setTimeout(() => {
      setPrepared({ key: preparationKey, markup: sanitizeSvgMarkup(svg, colorMode) });
    }, 0);
    return () => window.clearTimeout(preparationTimer);
  }, [colorMode, preparationKey, svg]);

  if (currentMarkup === null) {
    return <Text sx={{ color: "fg.muted", fontSize: 1 }}>图形准备中…</Text>;
  }

  if (!currentMarkup) {
    return <Text sx={{ color: "danger.fg", fontSize: 1 }}>SVG 内容无效，无法显示。</Text>;
  }

  return (
    <Box
      role="img"
      aria-label={label}
      className={`oops-svg is-${colorMode}`}
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
      dangerouslySetInnerHTML={{ __html: currentMarkup }}
    />
  );
}
