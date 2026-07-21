import { expect, test, type Page } from "@playwright/test";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.stack || error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("RDKit and TikZJax render non-empty SVG output", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/debug", { waitUntil: "domcontentloaded" });

  await expect(page.locator(".katex-error")).toHaveCount(0);
  await expect(page.getByText("流程图渲染失败", { exact: false })).toHaveCount(0);

  const molecule = page.getByRole("img", { name: "分子结构" });
  await expect(molecule).toBeVisible({ timeout: 60_000 });
  await expect(molecule.locator("svg path").first()).toBeAttached();

  const tikz = page.getByRole("img", { name: "TikZ 图形" });
  await expect(tikz).toBeVisible({ timeout: 90_000 });
  await expect(tikz.locator("svg path").first()).toBeAttached();

  const dimensions = await page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="img"] svg')).map((svg) => {
      const rect = svg.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(dimensions.length).toBeGreaterThanOrEqual(2);
  for (const dimension of dimensions) {
    expect(dimension.width).toBeGreaterThan(20);
    expect(dimension.height).toBeGreaterThan(20);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileLayout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    svgWidths: Array.from(document.querySelectorAll('[role="img"] svg')).map(
      (svg) => svg.getBoundingClientRect().width,
    ),
  }));
  expect(mobileLayout.scrollWidth).toBeLessThanOrEqual(mobileLayout.clientWidth);
  for (const width of mobileLayout.svgWidths) expect(width).toBeLessThanOrEqual(mobileLayout.clientWidth);

  const relevantErrors = errors.filter(
    (message) => !message.includes("/_next/webpack-hmr") && !message.includes("favicon"),
  );
  expect(relevantErrors, relevantErrors.join("\n\n")).toEqual([]);
});
