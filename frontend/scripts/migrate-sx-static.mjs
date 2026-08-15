import ts from "typescript";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const sourceRoots = ["app", "components", "features", "hooks", "lib"];
const dryRun = process.argv.includes("--dry-run");
const breakpoints = ["544px", "768px", "1024px", "1280px"];
const spacing = ["var(--oops-space-0)", "var(--oops-space-1)", "var(--oops-space-2)", "var(--oops-space-4)", "var(--oops-space-5)", "var(--oops-space-6)", "var(--oops-space-7)", "var(--oops-space-8)", "var(--oops-space-9)"];
const fontSizes = ["var(--oops-text-xs)", "var(--oops-text-sm)", "var(--oops-text-md)", "var(--oops-text-lg)", "var(--oops-text-xl)", "var(--oops-text-2xl)", "var(--oops-text-3xl)"];
const tokenMap = new Map([
  ["fg.default", "var(--fgColor-default)"], ["fg.muted", "var(--fgColor-muted)"], ["fg.accent", "var(--fgColor-accent)"],
  ["fg.success", "var(--fgColor-success)"], ["fg.danger", "var(--fgColor-danger)"], ["fg.attention", "var(--fgColor-attention)"],
  ["accent.fg", "var(--fgColor-accent)"], ["accent.emphasis", "var(--fgColor-accent-emphasis)"], ["accent.subtle", "var(--bgColor-accent-muted)"],
  ["canvas.default", "var(--bgColor-default)"], ["canvas.subtle", "var(--bgColor-muted)"], ["canvas.overlay", "var(--bgColor-overlay)"],
  ["bg.default", "var(--bgColor-default)"], ["bg.muted", "var(--bgColor-muted)"], ["border.default", "var(--borderColor-default)"],
  ["border.muted", "var(--borderColor-muted)"], ["danger.fg", "var(--fgColor-danger)"], ["danger.emphasis", "var(--fgColor-danger-emphasis)"],
  ["danger.subtle", "var(--bgColor-danger-muted)"], ["success.fg", "var(--fgColor-success)"], ["success.subtle", "var(--bgColor-success-muted)"],
  ["attention.fg", "var(--fgColor-attention)"], ["attention.subtle", "var(--bgColor-attention-muted)"], ["shadow.small", "var(--oops-shadow-sm)"],
  ["shadow.medium", "var(--oops-shadow-md)"],
]);
const aliases = new Map([["bg", "backgroundColor"], ["m", "margin"], ["mt", "marginTop"], ["mr", "marginRight"], ["mb", "marginBottom"], ["ml", "marginLeft"], ["mx", "marginInline"], ["my", "marginBlock"], ["p", "padding"], ["pt", "paddingTop"], ["pr", "paddingRight"], ["pb", "paddingBottom"], ["pl", "paddingLeft"], ["px", "paddingInline"], ["py", "paddingBlock"]]);
const unitless = new Set(["opacity", "zIndex", "fontWeight", "lineHeight", "flex", "order", "zoom"]);
const spacingProperties = new Set(["margin", "marginTop", "marginRight", "marginBottom", "marginLeft", "marginInline", "marginBlock", "padding", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "paddingInline", "paddingBlock", "gap", "rowGap", "columnGap"]);

function collectFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = join(directory, entry);
    if (statSync(absolute).isDirectory()) files.push(...collectFiles(absolute));
    else if (/\.(tsx?|jsx?)$/.test(entry) && !relative(frontendRoot, absolute).replaceAll("\\", "/").startsWith("components/ui/")) files.push(absolute);
  }
  return files;
}

function literalValue(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return { static: true, value: node.text };
  if (ts.isNumericLiteral(node)) return { static: true, value: Number(node.text) };
  if (node.kind === ts.SyntaxKind.TrueKeyword) return { static: true, value: true };
  if (node.kind === ts.SyntaxKind.FalseKeyword) return { static: true, value: false };
  if (node.kind === ts.SyntaxKind.NullKeyword) return { static: true, value: null };
  if (ts.isArrayLiteralExpression(node)) {
    const values = node.elements.map(literalValue);
    return values.every((item) => item.static) ? { static: true, value: values.map((item) => item.value) } : { static: false };
  }
  if (ts.isObjectLiteralExpression(node)) {
    const values = {};
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) return { static: false };
      const name = property.name && (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) ? property.name.text : null;
      if (!name) return { static: false };
      const value = literalValue(property.initializer);
      if (!value.static) return { static: false };
      values[name] = value.value;
    }
    return { static: true, value: values };
  }
  return { static: false };
}

function cssProperty(property) {
  return (aliases.get(property) ?? property).replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
}

function cssValue(property, value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") {
    if (value === "mono") return "var(--font-mono)";
    return tokenMap.get(value) ?? value;
  }
  const normalized = aliases.get(property) ?? property;
  if (normalized === "fontSize") return fontSizes[value] ?? `${value}px`;
  if (spacingProperties.has(normalized)) return spacing[value] ?? `${value}px`;
  if (unitless.has(normalized)) return String(value);
  return `${value}px`;
}

function selectorFor(parent, key) {
  if (key.includes("&")) return key.replaceAll("&", `.${parent}`);
  if (key.startsWith(":")) return `.${parent}${key}`;
  return `.${parent} ${key}`;
}

function rulesFor(style, className, media = null) {
  const declarations = [];
  const nested = [];
  for (const [property, rawValue] of Object.entries(style)) {
    if (rawValue === null || rawValue === undefined) continue;
    if (property.startsWith("@media")) {
      nested.push(`${property}{${rulesFor(rawValue, className)}}`);
      continue;
    }
    if (property.startsWith("@keyframes")) {
      const frames = Object.entries(rawValue).map(([step, frame]) => `${step}{${rulesFor(frame, className)}}`).join("");
      nested.push(`${property}{${frames}}`);
      continue;
    }
    if (property.startsWith("&") || property.startsWith(":") || ["input", "textarea", "button", "svg"].includes(property)) {
      nested.push(rulesFor(rawValue, selectorFor(className, property)));
      continue;
    }
    if (Array.isArray(rawValue)) {
      if (rawValue[0] !== undefined) declarations.push(`${cssProperty(property)}:${cssValue(property, rawValue[0])};`);
      rawValue.slice(1).forEach((value, index) => {
        if (value === undefined) return;
        nested.push(`@media (min-width: ${breakpoints[index]}){${rulesFor({ [property]: value }, className)}}`);
      });
      continue;
    }
    if (typeof rawValue === "object") {
      nested.push(rulesFor(rawValue, selectorFor(className, property)));
      continue;
    }
    declarations.push(`${cssProperty(property)}:${cssValue(property, rawValue)};`);
  }
  const current = declarations.length ? `.${className}{${declarations.join("")}}` : "";
  return `${media ? `${media}{` : ""}${current}${nested.join("")}${media ? "}" : ""}`;
}

function attrText(source, attribute) {
  return source.slice(attribute.getStart(), attribute.end);
}

function migrateFile(file) {
  const source = readFileSync(file, "utf8");
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  const css = [];
  let index = 0;
  function visit(node) {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const openingElement = ts.isJsxElement(node) ? node.openingElement : node;
      const attributes = openingElement.attributes.properties;
      const sx = attributes.find((item) => ts.isJsxAttribute(item) && item.name.text === "sx");
      if (sx && ts.isJsxAttribute(sx) && sx.initializer && ts.isJsxExpression(sx.initializer) && sx.initializer.expression && ts.isObjectLiteralExpression(sx.initializer.expression)) {
        const parsed = literalValue(sx.initializer.expression);
        if (parsed.static) {
          const className = `sx${++index}`;
          css.push(`/* Generated from ${relative(frontendRoot, file).replaceAll("\\", "/")} */\n${rulesFor(parsed.value, className)}\n`);
          const classAttribute = attributes.find((item) => ts.isJsxAttribute(item) && item.name.text === "className");
          if (classAttribute && ts.isJsxAttribute(classAttribute)) {
            const current = classAttribute.initializer;
            const currentText = current ? (ts.isStringLiteral(current) ? JSON.stringify(current.text) : current.getText(sourceFile).replace(/^\{/, "").replace(/\}$/, "")) : "undefined";
            edits.push({ start: classAttribute.getStart(sourceFile), end: classAttribute.end, text: `className={[${currentText}, sxStyles.${className}].filter(Boolean).join(" ")}` });
            edits.push({ start: sx.getStart(sourceFile), end: sx.end, text: "" });
          } else {
            edits.push({ start: sx.getStart(sourceFile), end: sx.end, text: `className={sxStyles.${className}}` });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  if (!edits.length) return { file, converted: 0, skipped: (source.match(/\bsx=\{/g) ?? []).length };
  const moduleName = `${basename(file, extname(file))}.sx.module.css`;
  const importMatch = [...sourceFile.statements].filter((statement) => ts.isImportDeclaration(statement)).at(-1);
  edits.push({ start: importMatch ? importMatch.end : 0, end: importMatch ? importMatch.end : 0, text: `${importMatch ? "\n" : ""}import sxStyles from "./${moduleName}";` });
  const nextSource = edits.sort((a, b) => b.start - a.start).reduce((result, edit) => result.slice(0, edit.start) + edit.text + result.slice(edit.end), source);
  if (!dryRun) {
    writeFileSync(file, nextSource);
    writeFileSync(join(dirname(file), moduleName), css.join("\n"));
  }
  return { file, converted: index, skipped: (source.match(/\bsx=\{/g) ?? []).length - index };
}

const results = sourceRoots.flatMap((root) => collectFiles(join(frontendRoot, root))).map(migrateFile);
console.log(JSON.stringify({ dryRun, converted: results.reduce((sum, item) => sum + item.converted, 0), skipped: results.reduce((sum, item) => sum + item.skipped, 0), files: results.filter((item) => item.converted || item.skipped).map((item) => ({ file: relative(frontendRoot, item.file).replaceAll("\\", "/"), ...item })) }, null, 2));
