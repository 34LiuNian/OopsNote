import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

const enabled = process.env.OOPSNOTE_CREDENTIALED_E2E === "1";
const imagePath = process.env.OOPSNOTE_CREDENTIALED_E2E_IMAGE?.trim();

if (!enabled) {
  throw new Error(
    "Credentialed E2E is disabled. Set OOPSNOTE_CREDENTIALED_E2E=1 to acknowledge real model usage.",
  );
}

if (!imagePath) {
  throw new Error(
    "Credentialed E2E requires OOPSNOTE_CREDENTIALED_E2E_IMAGE to name a real question image.",
  );
}

export default defineConfig({
  ...baseConfig,
  testDir: "./tests/credentialed",
  timeout: 10 * 60_000,
  expect: { timeout: 10 * 60_000 },
});
