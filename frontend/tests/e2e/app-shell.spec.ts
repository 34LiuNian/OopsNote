import { expect, test, type Page } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

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
  await waitForAppReady(page);
  await expect(page.getByRole("heading", { name: "新建题目" })).toBeVisible();

  const relevantErrors = errors.filter((message) => !message.includes("/_next/webpack-hmr"));
  expect(relevantErrors, relevantErrors.join("\n\n")).toEqual([]);
});

test("desktop brand controls the sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const toggle = page.locator(".oops-titlebar__brand-toggle");
  const brandIcon = toggle.locator(".oops-titlebar__brand-icon");
  const brandMark = toggle.locator(".oops-titlebar__brand-mark");
  const brandAction = toggle.locator(".oops-titlebar__brand-action");

  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(toggle.locator("p")).toHaveCSS("font-size", "40px");
  await expect(brandIcon).toHaveCSS("width", "28px");
  await expect(brandIcon).toHaveCSS("height", "28px");

  await brandIcon.hover();
  await expect(brandMark).toHaveCSS("opacity", "0");
  await expect(brandAction).toHaveCSS("opacity", "1");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#oops-primary-sidebar")).toHaveClass(/is-collapsed/);
  await expect(toggle.locator("p")).toHaveText("OopsNote");
  await expect(toggle.locator("p")).toBeHidden();
  await expect(brandIcon).toBeVisible();

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#oops-primary-sidebar")).not.toHaveClass(/is-collapsed/);
  await expect(toggle.locator("p")).toBeVisible();
});

test("desktop content scroll keeps the rounded shell edge fixed", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const surface = page.locator(".oops-content-surface");
  const initialBounds = (await surface.boundingBox())!;
  await surface.evaluate((element) => {
    const spacer = document.createElement("div");
    spacer.style.height = "1600px";
    spacer.style.flex = "0 0 1600px";
    element.append(spacer);
    element.scrollTop = 500;
  });

  const scrolledState = await surface.evaluate((element) => ({
    borderRadius: getComputedStyle(element).borderRadius,
    boxShadow: getComputedStyle(element).boxShadow,
    scrollTop: element.scrollTop,
    top: element.getBoundingClientRect().top,
    windowScrollY: window.scrollY,
  }));
  expect(scrolledState.scrollTop).toBeGreaterThan(0);
  expect(scrolledState.windowScrollY).toBe(0);
  expect(scrolledState.top).toBeCloseTo(initialBounds.y, 1);
  expect(scrolledState.borderRadius).toBe("16px 0px 0px");
  expect(scrolledState.boxShadow).not.toBe("none");
});

test("splash remains visible while hydration scripts are still loading", async ({ page }) => {
  let delayedFirstScript = false;
  await page.route("**/_next/**/*.js*", async (route) => {
    if (delayedFirstScript) {
      await route.continue();
      return;
    }
    delayedFirstScript = true;
    await new Promise((resolve) => setTimeout(resolve, 1_800));
    await route.continue();
  });

  await page.goto("/", { waitUntil: "commit" });
  const splash = page.locator("#oops-splash");
  await splash.waitFor({ state: "visible" });
  await page.waitForTimeout(1_300);
  await expect(splash).toBeVisible();

  await page.waitForLoadState("load");
  await expect(splash).toBeHidden();
});

test("mobile shell fits without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);
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
  await waitForAppReady(page);
  await expect(page.getByRole("heading", { name: "批量扫描" })).toBeVisible();
  await expect(page.locator('input[type="file"][accept*="application/pdf"]')).toBeAttached();
  await expect(page.getByRole("button", { name: "开始处理" })).toHaveCount(0);

  const relevantErrors = errors.filter((message) => !message.includes("/_next/webpack-hmr"));
  expect(relevantErrors, relevantErrors.join("\n\n")).toEqual([]);
});
