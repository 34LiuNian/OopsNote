import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => readFileSync(resolve(root, file), "utf8");
const failures = [];

const notifySource = read("lib/notify.ts");
const policySource = read("lib/notificationPolicy.ts");
const bannerSource = read("components/ui/ErrorBanner.tsx");
const querySource = read("lib/queryClient.ts");
const monitorSource = read("components/ui/GlobalErrorMonitor.tsx");
const notificationHost = read("components/ui/MantineNotifications.tsx");

if (!/color === "red" \? false/.test(policySource)) failures.push("red notification policy must force autoClose=false");
if (!/errorNotificationId/.test(notifySource)) failures.push("notify.error must use stable error IDs");
if (!/notify\.error/.test(bannerSource) || !/return null/.test(bannerSource)) failures.push("ErrorBanner must bridge to notify.error without a second inline renderer");
if (!/QueryCache/.test(querySource) || !/MutationCache/.test(querySource)) failures.push("React Query cache failures must report globally");
if (!/addEventListener\("error"/.test(monitorSource) || !/unhandledrejection/.test(monitorSource)) failures.push("browser-level failures must report globally");
const notificationLimit = Number(notificationHost.match(/limit=\{(\d+)\}/)?.[1] || 0);
if (notificationLimit < 6) failures.push("notification host must keep enough persistent errors visible");

for (const file of ["app/login/page.tsx", "app/register/page.tsx"]) {
  const source = read(file);
  if (/role=["']alert["']/.test(source) || /styles\.error/.test(source)) failures.push(`${file} duplicates the persistent error notification with a page-level red banner`);
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
