import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const sourceRoots = ["app", "components", "features", "hooks", "lib"];
const publicSourceExtensions = new Set([".ts", ".tsx"]);
const failures = [];
const allowedMantineFiles = new Set([
  "components/providers/ThemeProvider.tsx",
  "components/ui/primitives.tsx",
  "components/ui/MantineNotifications.tsx",
  "components/ui/RenameDialog.tsx",
  "lib/notify.ts",
  "app/layout.tsx",
]);

function collectFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = join(directory, entry);
    if (statSync(absolute).isDirectory()) files.push(...collectFiles(absolute));
    else if (publicSourceExtensions.has(extname(entry))) files.push(absolute);
  }
  return files;
}

function relativeFile(absolute) {
  return relative(frontendRoot, absolute).replaceAll("\\", "/");
}

for (const absolute of sourceRoots.flatMap((root) => collectFiles(join(frontendRoot, root)))) {
  const file = relativeFile(absolute);
  const source = readFileSync(absolute, "utf8");
  if (/from\s+["']@mantine\/(?:core|hooks|modals|notifications)["']/.test(source) && !allowedMantineFiles.has(file)) {
    failures.push(`${file}: direct Mantine import belongs behind components/ui`);
  }
}

let diff = "";
try {
  diff = execFileSync("git", ["diff", "--no-ext-diff", "--unified=0", "--", "frontend"], { cwd: resolve(frontendRoot, ".."), encoding: "utf8" });
} catch {
  diff = "";
}

let currentFile = "";
const originalLineCache = new Map();
function lineExistsInHead(file, line) {
  if (!originalLineCache.has(file)) {
    try {
      const source = execFileSync("git", ["show", `HEAD:${file}`], { cwd: resolve(frontendRoot, ".."), encoding: "utf8" });
      originalLineCache.set(file, new Set(source.split(/\r?\n/).map((item) => item.trim())));
    } catch {
      originalLineCache.set(file, new Set());
    }
  }
  return originalLineCache.get(file).has(line.trim());
}

for (const line of diff.split(/\r?\n/)) {
  if (line.startsWith("+++ b/")) {
    currentFile = line.slice(6).replaceAll("\\", "/");
    continue;
  }
  if (!line.startsWith("+") || line.startsWith("+++")) continue;
  const added = line.slice(1);
  if (currentFile.includes("components/ui/")) continue;
  if (/\bsx=\{/.test(added) && !lineExistsInHead(currentFile, added)) failures.push(`${currentFile}: new business sx escape; use semantic UI props or feature geometry class`);
  if (/<(?:button|input|select|textarea)\b/.test(added) && !lineExistsInHead(currentFile, added)) failures.push(`${currentFile}: new native control; use the components/ui facade`);
}

const inventory = { sx: 0, nativeControls: 0 };
for (const absolute of sourceRoots.flatMap((root) => collectFiles(join(frontendRoot, root)))) {
  const file = relativeFile(absolute);
  const source = readFileSync(absolute, "utf8");
  if (file.includes("components/ui/")) continue;
  inventory.sx += source.match(/\bsx=\{/g)?.length ?? 0;
  inventory.nativeControls += source.match(/<(?:button|input|select|textarea)\b/g)?.length ?? 0;
}

if (failures.length) {
  console.error("UI boundary audit failed:\n\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log(`UI boundary audit passed (legacy inventory: ${inventory.sx} sx, ${inventory.nativeControls} native controls; no new escapes).`);
}
