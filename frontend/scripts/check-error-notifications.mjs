import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => readFileSync(resolve(root, file), "utf8");
const failures = [];

function collectSourceFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = resolve(directory, entry);
    if (statSync(absolute).isDirectory()) files.push(...collectSourceFiles(absolute));
    else if (/\.(tsx?|jsx?)$/.test(entry)) files.push(absolute);
  }
  return files;
}

const notifySource = read("lib/notify.ts");
const policySource = read("lib/notificationPolicy.ts");
const bannerSource = read("components/ui/ErrorBanner.tsx");
const querySource = read("lib/queryClient.ts");
const monitorSource = read("components/ui/GlobalErrorMonitor.tsx");
const notificationHost = read("components/ui/MantineNotifications.tsx");

if (!/color === "red" \? false/.test(policySource)) failures.push("red notification policy must force autoClose=false");
if (!/errorNotificationId/.test(notifySource)) failures.push("notify.error must use stable error IDs");
if (/notify\.error/.test(bannerSource) || !/role="alert"/.test(bannerSource)) failures.push("ErrorBanner must render the owning page error without creating a notification");
if (!/queryCache:\s*new QueryCache\(\)/.test(querySource) || !/mutationCache:\s*new MutationCache\(\)/.test(querySource)) failures.push("React Query cache must not add a second global error notification path");
if (!/addEventListener\("error"/.test(monitorSource) || !/unhandledrejection/.test(monitorSource) || !/console\.error/.test(monitorSource) || !/notifyRequestError/.test(monitorSource)) failures.push("browser-level failures must report through notify.error and preserve console evidence");
for (const file of [
  "components/renderers/TikzRenderer.tsx",
  "components/renderers/Mermaid.tsx",
  "components/renderers/MoleculeRenderer.tsx",
  "components/renderers/SvgMarkup.tsx",
  "components/renderers/LatexAssetRenderer.tsx",
]) {
  if (!/useRenderErrorNotification/.test(read(file))) {
    failures.push(`${file} must raise a persistent notification for local rendering failures`);
  }
}
const notificationLimit = Number(notificationHost.match(/limit=\{(\d+)\}/)?.[1] || 0);
if (notificationLimit < 6) failures.push("notification host must keep enough persistent errors visible");

for (const file of ["app/login/page.tsx", "app/register/page.tsx"]) {
  const source = read(file);
  if (/role=["']alert["']/.test(source) || /styles\.error/.test(source)) failures.push(`${file} duplicates the persistent error notification with a page-level red banner`);
}

for (const directory of ["app", "components", "features", "hooks", "lib"]) {
  for (const absolute of collectSourceFiles(resolve(root, directory))) {
    const relativeFile = absolute.slice(root.length + 1).replaceAll("\\", "/");
    if (relativeFile.startsWith("components/ui/")) continue;
    const source = readFileSync(absolute, "utf8");
    if (/role\s*=\s*["']alert["']/.test(source)) {
      failures.push(`${relativeFile} renders a business-level alert DOM; use ErrorBanner or a field error prop so the global notification remains authoritative`);
    }
  }
}

const silentCatchAllowlist = new Set([
  "components/renderers/LiveStreamRenderer.tsx",
  "features/tasks/useActiveTaskList.ts",
  "lib/derived-svg-cache.ts",
]);
const sourceFiles = [
  "components/renderers/LiveStreamRenderer.tsx",
  "features/tasks/useActiveTaskList.ts",
  "lib/derived-svg-cache.ts",
  "lib/auth.ts",
];
for (const file of sourceFiles) {
  const source = read(file);
  if (/catch\s*\{\s*(?:\/\/[^\n]*\s*)?\}/.test(source) && !silentCatchAllowlist.has(file)) {
    failures.push(`${file} contains an unclassified silent catch`);
  }
}

if (failures.length) {
  console.error("Error notification audit failed:\n\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log("Error notification audit passed (persistent policy, global bridges, and auth duplication checks). ");
}
