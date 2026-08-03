import type { Page } from "@playwright/test";

// Splash fallback is 10s, followed by a 0.9s exit animation. Keep this
// timeout local to app readiness so unrelated assertions remain strict.
const APP_READY_TIMEOUT_MS = 13_000;

export async function waitForAppReady(page: Page): Promise<void> {
  await page.locator("#oops-splash").waitFor({
    state: "hidden",
    timeout: APP_READY_TIMEOUT_MS,
  });
}
