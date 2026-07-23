import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number(process.env.OOPSNOTE_FRONTEND_PORT ?? "3000");
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npm run dev -- -p ${frontendPort}`,
    url: frontendUrl,
    env: {
      ...process.env,
      NEXT_DIST_DIR: process.env.OOPSNOTE_NEXT_DIST_DIR ?? ".next",
    },
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], channel: process.platform === "win32" ? "msedge" : undefined },
    },
    {
      name: "firefox",
      testMatch: /batch-cross-page\.spec\.ts/,
      use: { ...devices["Desktop Firefox"] },
    },
  ],
});
