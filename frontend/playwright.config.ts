import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number(process.env.OOPSNOTE_FRONTEND_PORT ?? "3000");
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const browserChannel = process.env.OOPSNOTE_BROWSER_CHANNEL === "none"
  ? undefined
  : process.env.OOPSNOTE_BROWSER_CHANNEL ?? (process.platform === "win32" ? "msedge" : undefined);

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
    command: `npm run dev -- --port ${frontendPort}`,
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
      use: { ...devices["Desktop Chrome"], ...(browserChannel ? { channel: browserChannel } : {}) },
    },
  ],
});
