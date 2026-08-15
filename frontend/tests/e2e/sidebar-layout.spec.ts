import { expect, test, type Page } from "@playwright/test";

async function mockLibraryApis(page: Page) {
  await page.route("**/api/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(/\/api\/problems(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route(/\/api\/tasks(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
}

test("L1 is scoped to library while L0 remains the primary navigation", async ({ page }) => {
  await mockLibraryApis(page);
  await page.goto("/library", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("题库筛选", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "快捷导航" })).toBeVisible();

  await page.goto("/papers", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-secondary-sidebar")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
});

test("library sidebar layers can be controlled independently on desktop", async ({ page }) => {
  await mockLibraryApis(page);
  await page.goto("/library", { waitUntil: "domcontentloaded" });

  const primarySidebar = page.locator("#oops-primary-sidebar");
  const secondarySidebar = page.locator("#oops-secondary-sidebar");
  const primaryToggle = page.getByRole("button", { name: "展开侧栏" });

  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);
  await expect(secondarySidebar).toHaveCSS("margin-top", "16px");
  await expect(primaryToggle).toBeVisible();
  await expect(page.getByRole("button", { name: "筛选", exact: true })).toHaveAttribute("aria-pressed", "true");

  await primaryToggle.click();
  await expect(primarySidebar).not.toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);
  await page.getByRole("button", { name: "收起侧栏" }).click();
  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);

  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).toHaveClass(/is-closed/);
  await expect(page.getByRole("button", { name: "筛选", exact: true })).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);
  await expect(page.getByRole("button", { name: "筛选", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "收起题库筛选" }).click();
  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).toHaveClass(/is-closed/);

  await page.getByRole("link", { name: "题库", exact: true }).click();
  await expect(primarySidebar).toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);
});

test("AI channels keeps L0 and a wider L1 visible together", async ({ page }) => {
  await page.goto("/settings/channels", { waitUntil: "domcontentloaded" });

  const primarySidebar = page.locator("#oops-primary-sidebar");
  const secondarySidebar = page.locator("#oops-secondary-sidebar");

  await expect(primarySidebar).not.toHaveClass(/is-collapsed/);
  await expect(secondarySidebar).not.toHaveClass(/is-closed/);
  await expect(secondarySidebar).toHaveCSS("width", "312px");
  await expect(secondarySidebar).toHaveCSS("margin-top", "16px");
});

test("library filters become an explicit drawer on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockLibraryApis(page);
  await page.goto("/library", { waitUntil: "domcontentloaded" });

  const secondarySidebar = page.locator("#oops-secondary-sidebar");
  await expect(secondarySidebar).not.toHaveClass(/is-mobile-open/);

  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(secondarySidebar).toHaveClass(/is-mobile-open/);
  await expect(page.getByText("题库筛选", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "收起题库筛选" }).click();
  await expect(secondarySidebar).not.toHaveClass(/is-mobile-open/);
});
