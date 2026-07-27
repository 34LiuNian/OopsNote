import { expect, test } from "@playwright/test";

type ProblemFixture = {
  task_id: string;
  problem_id: string;
  question_no: string;
  question_type: string;
  content_format: "oopsmark-v1";
  problem_text: string;
  options: Array<{ key: string; text: string }>;
  subject: string;
  source: string;
  knowledge_points: string[];
  knowledge_tags: string[];
  error_tags: string[];
  user_tags: string[];
  created_at: string;
};

function problemFixture(index: number): ProblemFixture {
  return {
    task_id: `task-${index}`,
    problem_id: `problem-${index}`,
    question_no: String(index),
    question_type: "解答题",
    content_format: "oopsmark-v1",
    problem_text: `测试题目 ${index}`,
    options: [],
    subject: "math",
    source: "批量操作测试",
    knowledge_points: [],
    knowledge_tags: [],
    error_tags: [],
    user_tags: [],
    created_at: `2026-07-2${index}T10:00:00+08:00`,
  };
}

test("library batch deletion keeps failed items selected for an explicit retry", async ({ page }) => {
  let problems = [problemFixture(1), problemFixture(2), problemFixture(3)];
  let taskTwoFailuresRemaining = 1;

  await page.route("**/api/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(/\/api\/problems(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: problems } });
  });
  await page.route(/\/api\/tasks(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route(/\/api\/tasks\/task-\d+$/, async (route) => {
    const taskId = route.request().url().split("/").at(-1)!;
    if (taskId === "task-2" && taskTwoFailuresRemaining > 0) {
      taskTwoFailuresRemaining -= 1;
      await route.fulfill({ status: 409, json: { detail: "Cancel the active task before deleting it" } });
      return;
    }
    problems = problems.filter((problem) => problem.task_id !== taskId);
    await route.fulfill({ json: { success: true } });
  });

  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "批量操作" })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看任务" })).toHaveCount(3);

  await page.getByRole("button", { name: "批量操作" }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(3);
  await expect(page.getByRole("link", { name: "查看任务" })).toHaveCount(0);
  await page.getByRole("button", { name: "全选", exact: true }).click();
  await expect(page.getByText("已选 3 项", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "选择题目 3" }).click();
  await expect(page.getByText("已选 2 项", { exact: true })).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除 (2)" }).click();

  await expect(page.getByText("已选 1 项", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(2);
  await expect(page.getByRole("checkbox", { name: "选择题目 2" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "选择题目 3" })).not.toBeChecked();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除 (1)" }).click();

  await expect(page.getByRole("button", { name: "批量操作" })).toBeVisible();
  await expect(page.getByText("测试题目 3", { exact: true })).toBeVisible();
  await expect(page.getByText("测试题目 2", { exact: true })).toHaveCount(0);
});
