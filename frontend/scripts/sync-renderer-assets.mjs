import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const assets = [
  ["node_modules/@rdkit/rdkit/dist/RDKit_minimal.js", "public/vendor/rdkit/RDKit_minimal.js"],
  ["node_modules/@rdkit/rdkit/dist/RDKit_minimal.wasm", "public/vendor/rdkit/RDKit_minimal.wasm"],
  ["node_modules/isomorphic-tikzjax/tex", "public/vendor/tikzjax/tex"],
  ["node_modules/isomorphic-tikzjax/css", "public/vendor/tikzjax/css"],
];

for (const [source, target] of assets) {
  const from = join(root, source);
  const to = join(root, target);
  await rm(to, { recursive: true, force: true });
  await mkdir(dirname(to), { recursive: true });
  await cp(from, to, { recursive: true });
}

await build({
  entryPoints: [join(root, "components/renderers/TikzWorker.ts")],
  outfile: join(root, "public/vendor/tikzjax/worker.js"),
  bundle: true,
  minify: true,
  platform: "browser",
  format: "iife",
  target: ["chrome90", "firefox90", "safari16"],
  alias: { "node:buffer": "buffer" },
  external: ["jsdom", "svgo"],
});
