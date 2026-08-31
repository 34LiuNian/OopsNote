import { expect, test } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

test("source filtering uses document names and does not emit border style warnings", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const problem = (index: number, source: string) => ({
    task_id: `task-${index}`,
    problem_id: `problem-${index}`,
    question_no: String(index),
    question_type: "解答题",
    content_format: "oopsmark-v1",
    problem_text: `第 ${index} 道题`,
    options: [],
    subject: "math",
    source,
    knowledge_points: [],
    knowledge_tags: [],
    error_tags: [],
    user_tags: [],
    created_at: `2026-07-2${index}T10:00:00+08:00`,
  });

  await page.route("**/api/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route("**/api/tasks?*", async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/tags?*", async (route) => {
    const url = new URL(route.request().url());
    const items = url.searchParams.get("dimension") === "meta"
      ? [{ id: "source-pdf", dimension: "meta", value: "questions.pdf", aliases: [], source: "derived", ref_count: 1 }]
      : [];
    await route.fulfill({ json: { items } });
  });
  await page.route("**/api/problems*", async (route) => {
    const url = new URL(route.request().url());
    const filtered = url.searchParams.getAll("source").length > 0;
    await route.fulfill({
      json: {
        items: filtered
          ? [problem(1, "questions.pdf")]
          : [problem(1, "questions.pdf"), problem(2, "another.pdf")],
      },
    });
  });

  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);
  await expect(page.getByText("第 2 道题", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "筛选" }).click();
  await page.getByRole("button", { name: "更多筛选" }).click();
  const sourceInput = page.getByRole("textbox", { name: "来源标签输入" });
  await sourceInput.focus();
  await page.getByRole("option", { name: /questions\.pdf/ }).click();
  await expect(page.getByText("第 2 道题", { exact: true })).toHaveCount(0);

  const styleWarnings = consoleErrors.filter((message) => message.includes("Updating a style property during rerender"));
  expect(styleWarnings, styleWarnings.join("\n\n")).toEqual([]);
});
