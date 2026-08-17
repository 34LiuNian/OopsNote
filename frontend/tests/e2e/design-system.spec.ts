import { expect, test } from "@playwright/test";

async function mockAuthenticatedSession(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/get-session*", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session: { id: "design-system-session", userId: "design-system-user" },
        user: { id: "design-system-user", name: "Design System", email: "design@example.test", role: "admin" },
      }),
    });
  });
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ json: { status: "ok" } });
  });
}

test.describe("Graphite Workbench design system matrix", () => {
  test("covers focus, persistent errors, and mobile overflow", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.goto("/debug", { waitUntil: "domcontentloaded" });

    const matrix = page.getByTestId("design-system-matrix");
    await expect(matrix).toBeVisible({ timeout: 30_000 });
    await expect(matrix.getByRole("button", { name: "Save settings" })).toBeVisible();
    const firstInput = matrix.getByRole("textbox").first();
    await firstInput.focus();
    await expect(firstInput).toBeFocused();

    await matrix.getByRole("button", { name: "Trigger persistent error" }).click();
    const notification = page.getByText("Matrix error", { exact: true });
    await expect(notification).toBeVisible();
    await page.waitForTimeout(3_000);
    await expect(notification).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    const layout = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      overflowing: Array.from(document.querySelectorAll<HTMLElement>("body *"))
        .map((element) => ({ tag: element.tagName, className: element.className, width: element.getBoundingClientRect().width, right: element.getBoundingClientRect().right }))
        .filter((item) => item.right > document.documentElement.clientWidth + 1)
        .slice(0, 8),
    }));
    expect(layout.scrollWidth, JSON.stringify(layout.overflowing)).toBeLessThanOrEqual(layout.clientWidth);
  });

  test("respects reduced motion and dialog focus", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });
    await page.goto("/debug", { waitUntil: "domcontentloaded" });

    const matrix = page.getByTestId("design-system-matrix");
    await expect(matrix).toBeVisible({ timeout: 30_000 });
    await matrix.getByRole("button", { name: "Open Dialog" }).click();
    const dialog = page.getByRole("dialog", { name: "Dialog state matrix" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("preserve focus");
    await expect(page.locator("html")).toHaveAttribute("data-oopsnote-color-scheme", "dark");
  });
});
