import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoots = ["app", "components", "features", "hooks", "lib"];
const sourceExtensions = new Set([".css", ".ts", ".tsx"]);

// These boundaries render pixels or browser metadata. They do not define UI chrome.
const rawColorExceptions = new Map([
  ["app/design-tokens.css", "authoritative raw token source"],
  ["app/layout.tsx", "browser theme-color metadata cannot consume CSS variables"],
  ["app/manifest.ts", "web manifest colors cannot consume CSS variables"],
  ["app/icon.tsx", "generated application icon pixels"],
  ["app/apple-icon.tsx", "generated application icon pixels"],
  ["app/icon-light/route.tsx", "generated application icon pixels"],
  ["app/icon-dark/route.tsx", "generated application icon pixels"],
  ["app/debug/page.tsx", "inline SVG renderer fixture"],
  ["app/papers/paperWorkflow.module.css", "print-paper rendering surface"],
  ["app/papers/paperEditor.module.css", "print-paper rendering surface"],
  ["components/renderers/SvgMarkup.tsx", "sanitized source-SVG color normalization"],
  ["components/image-selection/imageSelection.css", "source-image selection overlay"],
  ["components/batch-continuous/batchContinuous.css", "source-image selection and processing overlay"],
]);

const gradientExceptions = new Map([
  ["app/papers/paperWorkflow.module.css", "difficulty distribution data track"],
  ["components/batch-continuous/batchContinuous.css", "selection masks and active-processing border"],
]);

const ALLOWED_FONT_PX = new Set([12, 13, 14, 16, 20, 24, 32, 40]);
const ALLOWED_RADIUS_PX = new Set([0, 4, 6, 8, 12, 16]);
const fontSizeExceptions = new Map([
  ["components/settings/ai/aiSettings.module.css", "3px credential mask hides secret glyphs without a second input type"],
]);

function collectFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = join(directory, entry);
    if (statSync(absolute).isDirectory()) {
      files.push(...collectFiles(absolute));
    } else if (sourceExtensions.has(extname(entry))) {
      files.push(absolute);
    }
  }
  return files;
}

function lineNumber(source, index) {
  return source.slice(0, index).split("\n").length;
}

function findMatches(source, pattern) {
  return [...source.matchAll(pattern)].map((match) => ({
    line: lineNumber(source, match.index ?? 0),
    value: match[0].trim(),
  }));
}

const files = sourceRoots.flatMap((root) => collectFiles(join(frontendRoot, root)));
const failures = [];

for (const absolute of files) {
  const file = relative(frontendRoot, absolute).replaceAll("\\", "/");
  const source = readFileSync(absolute, "utf8");

  if (!rawColorExceptions.has(file)) {
    for (const match of findMatches(source, /#[0-9a-f]{3,8}\b|rgba?\(/gi)) {
      failures.push(`${file}:${match.line} raw color ${match.value}`);
    }
  }

  if (!gradientExceptions.has(file)) {
    for (const match of findMatches(source, /\b(?:linear|radial|conic)-gradient\(/gi)) {
      failures.push(`${file}:${match.line} undocumented gradient ${match.value}`);
    }
  }

  for (const match of source.matchAll(/letter-spacing\s*:\s*([^;}\n]+)/gi)) {
    if (!/^0(?:px|rem|em)?$/i.test(match[1].trim())) {
      failures.push(`${file}:${lineNumber(source, match.index ?? 0)} non-zero letter spacing ${match[0].trim()}`);
    }
  }
  for (const match of source.matchAll(/letterSpacing\s*:\s*([^,}\n]+)/g)) {
    if (!/^["']?0["']?$/.test(match[1].trim())) {
      failures.push(`${file}:${lineNumber(source, match.index ?? 0)} non-zero letter spacing ${match[0].trim()}`);
    }
  }

  if (file !== "app/design-tokens.css") {
    for (const match of findMatches(source, /--oops-(?:graphite-\d|space-\d|text-[\w-]+|radius-[\w-]+|shadow-[\w-]+|transition-[\w-]+)\s*:/g)) {
      failures.push(`${file}:${match.line} redeclared foundation token ${match.value}`);
    }
  }

  for (const match of findMatches(source, /\bGloock\b/g)) {
    failures.push(`${file}:${match.line} disallowed display font ${match.value}`);
  }

  if (file !== "app/design-tokens.css") {
    for (const match of source.matchAll(/font-size\s*:\s*([\d.]+)px/gi)) {
      const px = Number(match[1]);
      if (ALLOWED_FONT_PX.has(px)) continue;
      if (fontSizeExceptions.has(file) && px === 3) continue;
      failures.push(`${file}:${lineNumber(source, match.index ?? 0)} off-scale font-size ${match[0].trim()}`);
    }
    for (const match of source.matchAll(/border-radius\s*:\s*([^;}\n]+)/gi)) {
      const value = match[1].replace(/var\(--oops-radius-[\w-]+\)/g, "");
      for (const radius of value.matchAll(/([\d.]+)px/g)) {
        const px = Number(radius[1]);
        if (px === 999 || px === 9999 || ALLOWED_RADIUS_PX.has(px)) continue;
        failures.push(`${file}:${lineNumber(source, match.index ?? 0)} off-scale border-radius ${match[0].trim()}`);
      }
    }
  }
}

if (failures.length > 0) {
  console.error("Design system audit failed:\n");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  const exceptionCount = new Set([...rawColorExceptions.keys(), ...gradientExceptions.keys()]).size;
  console.log(`Design system audit passed (${files.length} files, ${exceptionCount} documented exceptions).`);
}
