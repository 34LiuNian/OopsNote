import { expect, test, type Page } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

const taskId = "task-progress-disclosures";

async function mockCompletedTask(page: Page) {
  const task = {
    id: taskId,
    status: "completed",
    stage: "done",
    stage_message: "处理完成",
    created_at: "2026-08-15T10:00:00+08:00",
    updated_at: "2026-08-15T10:01:25+08:00",
    run: {
      id: "run-progress-disclosures",
      attempt: 1,
      status: "completed",
      prompt_version: "test",
      duration_ms: 85000,
      heartbeat_at: "2026-08-15T10:01:25+08:00",
      ended_at: "2026-08-15T10:01:25+08:00",
      stages: [],
    },
    diagram_runs: [{
      id: "diagram-run-progress-disclosures",
      attempt: 1,
      purpose: "diagram",
      diagram_step: "review",
      status: "completed",
      prompt_version: "test",
      duration_ms: 18000,
      heartbeat_at: "2026-08-15T10:01:43+08:00",
      ended_at: "2026-08-15T10:01:43+08:00",
      stages: [],
    }],
    payload: {},
    problem: null,
    solution: null,
    tag: null,
  };

  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/auth/get-session*", async (route) => {
    await route.fulfill({
      json: {
        session: { id: "progress-session", userId: "progress-user" },
        user: { id: "progress-user", name: "Progress Test", email: "progress@example.test", role: "admin" },
      },
    });
  });
  await page.route(/\/api\/(?:backend\/)?health$/, async (route) => {
    await route.fulfill({ json: { status: "ok" } });
  });
  await page.route(/\/api\/(?:backend\/)?settings\/tag-dimensions$/, async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(new RegExp(`/api/(?:backend/)?tasks/${taskId}$`), async (route) => {
    await route.fulfill({ json: { task } });
  });
}

test("completed task and TikZ progress disclose independently", async ({ page }) => {
  await mockCompletedTask(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/tasks/${taskId}`, { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const taskCard = page.locator(".oops-card").first();
  const taskSummary = taskCard.getByRole("button", { name: /4\/4 阶段完成/ });
  const diagramSummary = taskCard.getByRole("button", { name: /TikZ 题图重建.*已完成/ });

  await expect(taskSummary).toHaveAttribute("aria-expanded", "false");
  await expect(diagramSummary).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("OCR 识别", { exact: true })).toHaveCount(0);
  await expect(page.getByText("视觉复核", { exact: true })).toHaveCount(0);
  expect((await taskCard.boundingBox())?.height).toBeLessThan(100);

  await diagramSummary.click();
  await expect(diagramSummary).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("视觉复核", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("OCR 识别", { exact: true })).toHaveCount(0);

  await diagramSummary.click();
  await taskSummary.click();
  await expect(page.getByText("OCR 识别", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("视觉复核", { exact: true })).toHaveCount(0);

  await taskSummary.click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(taskSummary).toBeVisible();
  await expect(diagramSummary).toBeVisible();
  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);
});
