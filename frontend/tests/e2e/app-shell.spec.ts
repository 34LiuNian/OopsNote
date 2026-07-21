import { expect, test, type Page } from "@playwright/test";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error: Error) => errors.push(error.stack || error.message));
  page.on("console", (message: { type: () => string; text: () => string }) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("homepage hydrates and dismisses splash", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor();
  await expect(page.locator("#oops-splash")).toBeHidden();
  await expect(page.getByRole("heading", { name: "新建题目" })).toBeVisible();

  const relevantErrors = errors.filter((message) => !message.includes("/_next/webpack-hmr"));
  expect(relevantErrors, relevantErrors.join("\n\n")).toEqual([]);
});

test("mobile shell fits without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();
  await expect(page.locator(".oops-mobile-tabbar")).toBeVisible();
  await expect(page.locator("aside")).toBeHidden();

  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});

test("batch scan is a separate manual-segmentation workspace", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/batch-segment", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();
  await expect(page.getByRole("heading", { name: "批量扫描" })).toBeVisible();
  await expect(page.locator('input[type="file"][accept*="application/pdf"]')).toBeAttached();
  await expect(page.getByRole("button", { name: "开始处理" })).toHaveCount(0);

  const relevantErrors = errors.filter((message) => !message.includes("/_next/webpack-hmr"));
  expect(relevantErrors, relevantErrors.join("\n\n")).toEqual([]);
});
