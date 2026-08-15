import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const sourceRoots = ["app", "components", "features", "hooks", "lib", "types"];
const sourceExtensions = new Set([".css", ".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const mojibakeMarkers = /[\u951f\u9225\u20ac\ufffd\u68f0\u6d30\u9352\u6944\u7487\u93cc\u9354\u59d8\u614b\u95b2\u6ace\u93b5\u5674\u93bf\u7c31\u95c4\u6d58\u5bb8\u6924]/;

function collectFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const file = join(directory, entry);
    if (statSync(file).isDirectory()) files.push(...collectFiles(file));
    else if (sourceExtensions.has(file.slice(file.lastIndexOf(".")))) files.push(file);
  }
  return files;
}

const findings = [];
for (const root of sourceRoots) {
  for (const file of collectFiles(join(frontendRoot, root))) {
    const lines = readFileSync(file, "utf8").split(/\r?\n/);
    lines.forEach((line, index) => {
      if (mojibakeMarkers.test(line)) {
        findings.push(`${relative(frontendRoot, file).replaceAll("\\", "/")}:${index + 1}: ${line.trim()}`);
      }
    });
  }
}

if (findings.length > 0) {
  console.error("Potential mojibake found in frontend source:");
  console.error(findings.join("\n"));
  process.exitCode = 1;
} else {
  console.log("No potential mojibake found in frontend source.");
}
