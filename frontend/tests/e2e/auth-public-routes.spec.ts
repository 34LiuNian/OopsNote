import { expect, test } from "@playwright/test";

test("serves the public login page and Better Auth session endpoint", async ({ page, request }) => {
  const sessionResponse = await request.get("/api/auth/get-session");
  expect(sessionResponse.status()).toBe(200);

  const loginResponse = await page.goto("/login?returnTo=%2F", { waitUntil: "domcontentloaded" });
  expect(loginResponse?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "登录 OopsNote" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "用户名或邮箱" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "密码" })).toBeVisible();
});
