import { expect, test } from "@playwright/test";

test("completed task stays compact and editing replaces the reading card", async ({ page }) => {
  const taskId = "task-ui-test";
  const task = {
    id: taskId,
    status: "completed",
    stage: "done",
    stage_message: "处理完成",
    created_at: "2026-07-26T10:00:00+08:00",
    updated_at: "2026-07-26T10:00:12+08:00",
    payload: {},
    asset: null,
    trace: {
      kind: "batch_segment",
      screenshot_path: "/assets/task-ui-test.png",
      screenshot_filename: "task-ui-test.png",
      source_file_hash: "source-ui-test",
      source_file_name: "界面测试试卷.pdf",
      page_index: 1,
      question_no: 26,
      segment_id: "segment-ui-test",
      batch_session_available: true,
    },
    problem: {
      problem_id: "problem-ui-test",
      question_no: "26",
      question_type: "解答题",
      source: "界面测试试卷.pdf",
      problem_text: "求函数 $f(x)=x^2$ 的最小值。",
      content_format: "oopsmark-v1",
      options: [],
      knowledge_tags: ["函数"],
      error_tags: [],
      user_tags: [],
      diagram_detected: false,
      diagram_kind: null,
      diagram_tikz_source: null,
      diagram_svg: null,
      diagram_image_path: null,
      diagram_position: "right",
      diagram_scale_percent: null,
      diagram_render_status: null,
      diagram_error: null,
      diagram_needs_review: false,
    },
    solution: {
      problem_id: "problem-ui-test",
      answer: "$0$",
      explanation: "当 $x=0$ 时取得最小值。",
    },
    tag: { problem_id: "problem-ui-test", knowledge_points: ["函数"] },
  };

  await page.route("**/api/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(`**/api/tasks/${taskId}`, async (route) => {
    await route.fulfill({ json: { task } });
  });
  await page.route(`**/api/tasks/${taskId}/problem/override`, async (route) => {
    const update = route.request().postDataJSON();
    task.problem = { ...task.problem, ...update };
    await route.fulfill({ json: { task } });
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/tasks/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();

  const taskCard = page.locator(".oops-card").first();
  const progressSummary = taskCard.getByRole("button", { name: /处理完成.*5\/5 个阶段/ });
  await expect(progressSummary).toBeVisible();
  await expect(taskCard.getByText("界面测试试卷.pdf", { exact: true })).toHaveCount(0);
  await expect(page.getByText("界面测试试卷.pdf", { exact: true })).toBeVisible();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "定位到批量扫描" })).toBeVisible();
  await expect(page.getByText("OCR 识别", { exact: true })).toHaveCount(0);
  await progressSummary.click();
  await expect(page.getByText("OCR 识别", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).click();
  await expect(page.getByText("编辑题目", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "题目与解答" })).toHaveCount(0);
  await expect(page.getByText("收起答案与解析", { exact: true })).toHaveCount(0);

  const problemText = page.locator("textarea").first();
  await problemText.fill("求函数 $f(x)=x^2+1$ 的最小值。");
  await expect(page.getByText("有未保存的修改", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByRole("heading", { name: "题目与解答" })).toBeVisible();
  await expect(page.getByText("求函数", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).click();
  await page.locator("textarea").first().fill("尚未保存的题干");
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("放弃未保存的修改？");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "关闭" }).click();
  await expect(page.getByText("编辑题目", { exact: true })).toBeVisible();

  page.once("dialog", async (dialog) => dialog.accept());
  await page.getByRole("button", { name: "关闭" }).click();
  await expect(page.getByRole("heading", { name: "题目与解答" })).toBeVisible();
});
