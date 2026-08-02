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

test("diagram renderers follow dark theme without destroying semantic colors", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/debug", { waitUntil: "domcontentloaded" });

  const fixture = page.locator("#problem-illustration-auto");
  const axis = fixture.locator("#theme-axis");
  const background = fixture.locator("#theme-background");
  const coloredSeries = fixture.locator("#theme-series");
  await expect(axis).toHaveAttribute("stroke", "currentColor");
  await expect(background).toHaveAttribute("fill", "var(--oops-svg-background)");
  await expect(coloredSeries).toHaveAttribute("stroke", "#0ea5e9");
  await expect(page.locator('[data-mermaid-theme="light"]')).toBeVisible({ timeout: 30_000 });

  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-oopsnote-color-scheme", "dark");
  await expect(page.locator('[data-mermaid-theme="dark"]')).toBeVisible({ timeout: 30_000 });

  const computed = await fixture.evaluate((element) => {
    const axisElement = element.querySelector<SVGElement>("#theme-axis")!;
    const seriesElement = element.querySelector<SVGElement>("#theme-series")!;
    const backgroundElement = element.querySelector<SVGElement>("#theme-background")!;
    return {
      axis: getComputedStyle(axisElement).stroke,
      series: getComputedStyle(seriesElement).stroke,
      background: getComputedStyle(backgroundElement).fill,
    };
  });
  expect(computed.axis).not.toBe("rgb(0, 0, 0)");
  expect(computed.series).toBe("rgb(14, 165, 233)");
  expect(computed.background).not.toBe("rgb(255, 255, 255)");

  const molecule = page.getByRole("img", { name: "分子结构" });
  await expect(molecule).toBeVisible({ timeout: 60_000 });
  expect(await molecule.innerHTML()).toContain("currentColor");

  const tikz = page.getByRole("img", { name: "TikZ 图形" });
  await expect(tikz).toBeVisible({ timeout: 90_000 });
  expect(await tikz.innerHTML()).toContain("currentColor");
});

test("GFM tables show a cell grid and are centered", async ({ page }) => {
  await page.goto("/debug", { waitUntil: "domcontentloaded" });

  const table = page.locator(".oops-markdown table").first();
  await expect(table).toBeVisible();

  const layout = await table.evaluate((element) => {
    const tableStyle = getComputedStyle(element);
    const cellStyle = getComputedStyle(element.querySelector("td")!);
    const rect = element.getBoundingClientRect();
    const parentRect = element.parentElement!.getBoundingClientRect();
    return {
      borderStyle: tableStyle.borderTopStyle,
      borderWidth: tableStyle.borderTopWidth,
      cellBorderStyle: cellStyle.borderTopStyle,
      cellBorderWidth: cellStyle.borderTopWidth,
      centerOffset: Math.abs(rect.left + rect.width / 2 - (parentRect.left + parentRect.width / 2)),
    };
  });

  expect(layout.borderStyle).toBe("solid");
  expect(layout.borderWidth).not.toBe("0px");
  expect(layout.cellBorderStyle).toBe("solid");
  expect(layout.cellBorderWidth).not.toBe("0px");
  expect(layout.centerOffset).toBeLessThan(1);
});

test("problem illustrations support mutually exclusive right-side auto sizing and custom sizing", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/debug", { waitUntil: "domcontentloaded" });

  const automatic = page.locator("#problem-illustration-auto .problem-content__lead");
  await expect(automatic).toHaveClass(/is-right/);
  await expect(automatic.locator('[role="img"]')).toBeVisible();
  const automaticSizes = await automatic.evaluate((element) => ({
    content: element.querySelector<HTMLElement>(".problem-content__body")!.getBoundingClientRect().height,
    figure: element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect().height,
    figureWidth: element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect().width,
    leadWidth: element.getBoundingClientRect().width,
    leadRight: element.getBoundingClientRect().right,
    figureRight: element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect().right,
    optionsInsideContent: Boolean(element.querySelector(".problem-content__body [data-option-item='true']")),
  }));
  expect(automaticSizes.optionsInsideContent).toBe(true);
  expect(automaticSizes.figure).toBeCloseTo(automaticSizes.content, 0);
  expect(automaticSizes.figureWidth / automaticSizes.figure).toBeCloseTo(1.5, 1);
  expect(automaticSizes.figureWidth).toBeLessThanOrEqual(automaticSizes.leadWidth * 0.38 + 1);
  expect(automaticSizes.leadRight - automaticSizes.figureRight).toBeLessThan(1);

  const custom = page.locator("#problem-illustration-custom .problem-content__lead");
  await expect(custom).toHaveClass(/is-left/);
  await expect(custom.getByRole("img", { name: "附图" })).toBeVisible();
  const customSizes = await custom.evaluate((element) => ({
    content: element.querySelector<HTMLElement>(".problem-content__body")!.getBoundingClientRect().height,
    figure: element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect().height,
    figureWidth: element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect().width,
  }));
  expect(customSizes.figure / customSizes.content).toBeCloseTo(1.25, 1);
  expect(customSizes.figureWidth / customSizes.figure).toBeCloseTo(1, 1);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileSizes = await automatic.evaluate((element) => {
    const body = element.querySelector<HTMLElement>(".problem-content__body")!.getBoundingClientRect();
    const figure = element.querySelector<HTMLElement>(".problem-content__illustration")!.getBoundingClientRect();
    const lead = element.getBoundingClientRect();
    return {
      bodyBottom: body.bottom,
      figureTop: figure.top,
      figureWidth: figure.width,
      leadWidth: lead.width,
    };
  });
  expect(mobileSizes.figureTop).toBeGreaterThanOrEqual(mobileSizes.bodyBottom);
  expect(mobileSizes.figureWidth).toBeLessThanOrEqual(mobileSizes.leadWidth + 1);
});
