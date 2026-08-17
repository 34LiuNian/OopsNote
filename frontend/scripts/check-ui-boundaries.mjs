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

// Inline styles are restricted to runtime geometry. Existing framework and
// renderer boundary files remain explicit until their owning CSS module batch
// is complete; each entry carries an owner and removal condition.
const inlineStyleAllowlist = new Map([
  ["app/layout.tsx", "framework body canvas; owner: UI foundations; remove when root shell token is CSS-only"],
  ["app/apple-icon.tsx", "Next metadata renderer; owner: app shell; remove when metadata API supports tokens"],
  ["app/icon.tsx", "Next metadata renderer; owner: app shell; remove when metadata API supports tokens"],
  ["app/icon-dark/route.tsx", "Next metadata renderer; owner: app shell; remove when metadata API supports tokens"],
  ["app/icon-light/route.tsx", "Next metadata renderer; owner: app shell; remove when metadata API supports tokens"],
  ["components/ProblemEditPanel.tsx", "image fit geometry; owner: problem editor; geometry migration"],
  ["components/ProblemContent.tsx", "illustration ratio geometry; owner: renderer; geometry migration"],
  ["components/TaskThumbnail.tsx", "thumbnail dimensions; owner: library; geometry migration"],
  ["app/library/page.tsx", "task strip minimum geometry; owner: library; geometry migration"],
  ["app/paper-builder/page.tsx", "PDF viewport geometry; owner: paper builder; geometry migration"],
  ["app/papers/new/page.tsx", "paper canvas geometry; owner: paper builder; geometry migration"],
  ["app/papers/[draftId]/edit/page.tsx", "paper preview geometry; owner: paper builder; geometry migration"],
  ["app/settings/policy/page.tsx", "empty-state layout boundary; owner: settings; migrate with policy CSS module"],
  ["app/settings/channels/page.tsx", "channel detail layout boundary; owner: settings; migrate with channels CSS module"],
  ["features/upload/components/BatchScanForm.tsx", "crop and page ratio geometry; owner: batch scan; geometry migration"],
  ["features/papers/KnowledgeTreeSelector.tsx", "tree indentation geometry; owner: paper builder; geometry migration"],
  ["components/batch-continuous/BatchSelectionOverlay.tsx", "selection rectangle geometry; owner: batch scan; geometry migration"],
  ["components/batch-continuous/BatchContinuousSurface.tsx", "page and crop geometry; owner: batch scan; geometry migration"],
  ["components/image-selection/NormalizedRectEditor.tsx", "normalized rectangle geometry; owner: image selection; geometry migration"],
  ["components/task/TaskProgressBar.tsx", "step label geometry variables; owner: task workflow; geometry migration"],
  ["components/task/TaskMathRenderer.tsx", "hidden measurement node; owner: renderer; remove with measurement API"],
  ["components/task/TaskStatusNotifications.tsx", "notification progress content; owner: task workflow; migrate to notification content CSS"],
  ["components/settings/ai/ChannelRail.tsx", "channel rail layout boundary; owner: AI settings; migrate with rail CSS module"],
  ["components/settings/ai/ModelCatalog.tsx", "catalog layout boundary; owner: AI settings; migrate with catalog CSS module"],
  ["components/settings/ai/PolicyEditor.tsx", "policy layout boundary; owner: AI settings; migrate with policy CSS module"],
  ["components/settings/ai/ProviderMark.tsx", "provider mark dimensions; owner: AI settings; geometry migration"],
  ["components/task/ProblemStudyPanel.tsx", "task link presentation; owner: task workflow; migrate to task CSS module"],
  ["components/upload/UploadQueue.tsx", "native file input hiding; owner: upload; replace with facade input"],
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
  if (currentFile.endsWith(".css") && /\.mantine-Button-(?:inner|label)\b/.test(added) && !lineExistsInHead(currentFile, added)) {
    failures.push(`${currentFile}: Button internals belong behind components/ui; use semantic Button props`);
  }
  if (/\bsx=\{/.test(added) && !lineExistsInHead(currentFile, added)) failures.push(`${currentFile}: new business sx escape; use semantic UI props or feature geometry class`);
  if (/<(?:button|input|select|textarea)\b/.test(added) && !lineExistsInHead(currentFile, added)) failures.push(`${currentFile}: new native control; use the components/ui facade`);
}

const inventory = { sx: 0, nativeControls: 0 };
for (const absolute of sourceRoots.flatMap((root) => collectFiles(join(frontendRoot, root)))) {
  const file = relativeFile(absolute);
  const source = readFileSync(absolute, "utf8");
  if (file.includes("components/ui/")) continue;
  const sxMatches = source.match(/\bsx=\{/g)?.length ?? 0;
  inventory.sx += sxMatches;
  inventory.nativeControls += source.match(/<(?:button|input|select|textarea)\b/g)?.length ?? 0;
  if (sxMatches > 0) {
    const lines = source.split(/\r?\n/);
    lines.forEach((line, index) => {
      if (/\bsx=\{/.test(line)) failures.push(`${file}:${index + 1}: business sx is forbidden; use semantic UI props or feature geometry CSS`);
    });
  }
  const inlineStyleMatches = source.match(/\bstyle=\{\{/g)?.length ?? 0;
  if (inlineStyleMatches > 0 && !inlineStyleAllowlist.has(file)) {
    failures.push(`${file}: inline style is forbidden; use CSS Module or --oops-geometry-* variables`);
  }
}

if (inventory.nativeControls > 0) failures.push(`business source contains ${inventory.nativeControls} native interactive controls; use components/ui facade`);

if (failures.length) {
  console.error("UI boundary audit failed:\n\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log(`UI boundary audit passed (legacy inventory: ${inventory.sx} sx, ${inventory.nativeControls} native controls; inline-style allowlist: ${inlineStyleAllowlist.size}).`);
}
