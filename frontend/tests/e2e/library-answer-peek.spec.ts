import { expect, test } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

test("library reveals, expands, and caches a question answer", async ({ page }) => {
  let taskDetailRequests = 0;

  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/auth/get-session*", async (route) => {
    await route.fulfill({
      json: {
        session: { id: "library-session", userId: "library-user" },
        user: { id: "library-user", name: "Library User", email: "library@example.test", role: "admin" },
      },
    });
  });
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ json: { status: "ok" } });
  });
  await page.route("**/api/backend/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route("**/api/backend/tasks?*", async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/backend/problems*", async (route) => {
    await route.fulfill({
      json: {
        items: [{
          task_id: "task-1",
          problem_id: "problem-1",
          question_no: "8",
          question_type: "单选题",
          content_format: "oopsmark-v1",
          problem_text: "已知 $x=2$，求 $x^2$。",
          options: [],
          subject: "math",
          source: "期末复习.pdf",
          knowledge_points: [],
          created_at: "2026-08-19T10:00:00+08:00",
        }],
      },
    });
  });
  await page.route("**/api/backend/tasks/task-1", async (route) => {
    taskDetailRequests += 1;
    await route.fulfill({
      json: {
        task: {
          id: "task-1",
          status: "completed",
          subject: "math",
          created_at: "2026-08-19T10:00:00+08:00",
          updated_at: "2026-08-19T10:00:00+08:00",
          problem: {
            problem_id: "problem-1",
            content_format: "oopsmark-v1",
            problem_text: "已知 $x=2$，求 $x^2$。",
            options: [],
          },
          solution: {
            problem_id: "problem-1",
            answer: "第一空：$4$\n第二空：$5$",
            explanation: "将 $x=2$ 代入 $x^2$，得到 $4$。",
          },
          tag: null,
        },
      },
    });
  });

  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const row = page.locator("[class*='problemItem']").first();
  const answerToggle = row.getByRole("button", { name: "查看答案" });
  await expect(row.getByText("题型：", { exact: false })).toHaveCount(0);
  await expect(row.getByText("来源：", { exact: false })).toHaveCount(0);
  await expect(row.getByText("单选题", { exact: true })).toBeVisible();
  await expect(row.getByText("期末复习.pdf", { exact: true })).toBeVisible();
  await expect(answerToggle).toHaveCSS("opacity", "0");

  await row.hover();
  await expect(answerToggle).toBeVisible();
  await expect(answerToggle).toHaveCSS("opacity", "1");
  await answerToggle.click();
  await expect(row.getByText("答案", { exact: true })).toBeVisible();
  await expect(row.getByText("解析", { exact: true })).toBeVisible();
  await expect(row.getByText("收起答案", { exact: true })).toBeVisible();
  await expect(row.locator("[class*='answerPanel']").first()).toHaveClass(/answerPanelNoWrap/);
  await expect(row.locator("[class*='answerPanel'] section:first-of-type .oops-markdown p")).toHaveCSS("white-space", "nowrap");
  await expect(row.locator("[class*='answerPanel'] section:first-of-type .oops-markdown br")).toHaveCSS("display", "none");
  await expect(row.locator("[class*='answerSections']").first()).toHaveCSS("font-family", /Times New Roman/);
  expect(taskDetailRequests).toBe(1);

  await row.getByRole("button", { name: "收起答案" }).click();
  await expect(row.getByText("答案", { exact: true })).toHaveCount(0);
  await row.getByRole("button", { name: "查看答案" }).click();
  await expect(row.getByText("答案", { exact: true })).toBeVisible();
  expect(taskDetailRequests).toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(row.getByText("解析", { exact: true })).toBeVisible();
  const pageWidth = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(pageWidth.scrollWidth).toBeLessThanOrEqual(pageWidth.clientWidth);
});

test("paper builder uses the shared answer peek contract", async ({ page }) => {
  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/auth/get-session*", async (route) => {
    await route.fulfill({ json: { session: { id: "builder-session", userId: "builder-user" }, user: { id: "builder-user", name: "Builder User", email: "builder@example.test", role: "admin" } } });
  });
  await page.route("**/api/health", async (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/backend/settings/tag-dimensions", async (route) => route.fulfill({ json: { dimensions: {} } }));
  await page.route("**/api/backend/tags*", async (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/backend/tasks?*", async (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/backend/problems*", async (route) => route.fulfill({ json: { items: [{
    task_id: "builder-task",
    problem_id: "builder-problem",
    question_no: "1",
    question_type: "单选题",
    content_format: "oopsmark-v1",
    problem_text: "求 $1+1$。",
    options: [],
    subject: "math",
    source: "builder.pdf",
    knowledge_points: [],
    created_at: "2026-08-19T10:00:00+08:00",
  }] }}));
  await page.route("**/api/backend/tasks/builder-task", async (route) => route.fulfill({ json: { task: {
    id: "builder-task", status: "completed", subject: "math", created_at: "2026-08-19T10:00:00+08:00", updated_at: "2026-08-19T10:00:00+08:00",
    problem: { problem_id: "builder-problem", content_format: "oopsmark-v1", problem_text: "求 $1+1$。", options: [] },
    solution: { problem_id: "builder-problem", answer: "B", explanation: "直接计算。" }, tag: null,
  } } }));

  await page.goto("/paper-builder", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);
  const row = page.locator("li").filter({ hasText: "builder.pdf" }).first();
  await expect(row.getByText("单选题", { exact: true })).toBeVisible();
  await row.hover();
  await row.getByRole("button", { name: "查看答案" }).click();
  await expect(row.getByText("答案", { exact: true })).toBeVisible();
  await expect(row.getByText("解析", { exact: true })).toBeVisible();
});
