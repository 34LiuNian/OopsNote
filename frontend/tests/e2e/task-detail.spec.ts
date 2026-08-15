import { expect, test } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

test("completed task keeps a scaled diagram stable while editing replaces the reading card", async ({ page }) => {
  const taskId = "task-ui-test";
  const task = {
    id: taskId,
    status: "completed",
    stage: "done",
    stage_message: "处理完成",
    created_at: "2026-07-26T10:00:00+08:00",
    updated_at: "2026-07-26T10:00:12+08:00",
    run: {
      id: "run-ui-test",
      attempt: 1,
      status: "completed",
      prompt_version: "test",
      duration_ms: 63858,
      started_at: "2026-07-26T10:00:01+08:00",
      heartbeat_at: "2026-07-26T10:01:05+08:00",
      ended_at: "2026-07-26T10:01:05+08:00",
      stages: [],
    },
    payload: {},
    asset: {
      asset_id: "task-ui-test",
      source: "upload",
      path: "/assets/task-ui-test.png",
      mime_type: "image/png",
    },
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
      question_type: "单选题",
      source: "界面测试试卷.pdf",
      chapter: null as string | null,
      difficulty_coefficient_override: null as number | null,
      section_question_count: null as number | null,
      problem_text: "求函数 $f(x)=x^2$ 的最小值。",
      content_format: "oopsmark-v1",
      options: [
        { key: "A", text: "$\\frac{5}{2}$" },
        { key: "B", text: "3" },
      ],
      knowledge_tags: ["函数"],
      error_tags: [],
      user_tags: [],
      diagram_detected: false,
      diagram_kind: null,
      diagram_tikz_source: null,
      diagram_svg: null,
      diagram_image_path: null,
      diagram_image_crop: null as { x: number; y: number; width: number; height: number } | null,
      diagram_image_tone: "auto",
      diagram_position: "right",
      diagram_scale_percent: 200,
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

  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/settings/tag-dimensions", async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(`**/api/tasks/${taskId}`, async (route) => {
    await route.fulfill({ json: { task } });
  });
  await page.route(`**/api/tasks/${taskId}/duplicates`, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/assets/task-ui-test.png", async (route) => {
    await route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480"><rect width="800" height="480" fill="white"/><circle cx="400" cy="240" r="120" fill="none" stroke="black" stroke-width="8"/></svg>',
    });
  });
  await page.route(`**/api/tasks/${taskId}/problem/override`, async (route) => {
    const update = route.request().postDataJSON();
    const nextOptions = Array.isArray(update.options)
      ? update.options.map((text: string, index: number) => ({ key: String.fromCharCode(65 + index), text }))
      : task.problem.options;
    task.problem = { ...task.problem, ...update, options: nextOptions };
    await route.fulfill({ json: { task } });
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/tasks/${taskId}`, { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const taskCard = page.locator(".oops-card").first();
  const progressSummary = taskCard.getByRole("button", { name: /5\/5 阶段完成/ });
  await expect(progressSummary).toBeVisible();
  await expect(progressSummary).toContainText("1分3秒");
  await expect(taskCard.getByText("已完成", { exact: true })).toHaveCount(0);
  await expect(taskCard.getByText("处理完成", { exact: true })).toHaveCount(0);
  expect((await taskCard.boundingBox())?.height).toBeLessThan(100);
  await expect(taskCard.getByText("界面测试试卷.pdf", { exact: true })).toHaveCount(0);
  await expect(page.getByText("界面测试试卷.pdf", { exact: true })).toBeVisible();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "定位到批量扫描" })).toBeVisible();
  const problemHeading = page.getByRole("heading", { name: "题目与解答" });
  const taskCardBox = await taskCard.boundingBox();
  const problemHeadingBox = await problemHeading.boundingBox();
  if (!taskCardBox || !problemHeadingBox) throw new Error("任务详情布局未完成");
  expect(problemHeadingBox.y - (taskCardBox.y + taskCardBox.height)).toBeLessThan(40);
  await page.getByRole("button", { name: "举一反三" }).click();
  const variationDialog = page.getByRole("dialog", { name: "举一反三" });
  await expect(variationDialog).toBeVisible();
  await expect(variationDialog.getByLabel("变式方向")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(variationDialog).toHaveCount(0);
  await expect(page.locator("[data-option-item='true']").first().locator(".katex")).toBeVisible();
  await expect(page.getByText("OCR 识别", { exact: true })).toHaveCount(0);
  await progressSummary.click();
  await expect(taskCard.getByText("用时：1分3秒", { exact: true })).toBeVisible();
  await expect(page.getByText("OCR 识别", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).click();
  await expect(page.getByText("编辑题目", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "题目与解答" })).toHaveCount(0);
  await expect(page.getByText("收起答案与解析", { exact: true })).toHaveCount(0);
  await expect(page.getByText("支持 Markdown / LaTeX", { exact: false })).toHaveCount(0);
  await expect(page.getByText("未修改", { exact: true })).toHaveCount(0);
  await expect(page.locator(".option-editor__label")).toHaveText(["A", "B"]);
  await expect(page.getByRole("textbox", { name: "选项 A" })).toHaveValue("$\\frac{5}{2}$");
  await page.getByLabel("难度系数").fill("0.73");
  await page.getByLabel("章节").fill("函数");
  await page.getByLabel("区段总题数").fill("8");
  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.locator(".option-editor__label")).toHaveText(["A", "B", "C"]);
  await page.getByRole("button", { name: "删除选项 C" }).click();

  const problemText = page.locator("textarea").first();
  await expect(problemText).toHaveCSS("resize", "vertical");
  await expect(page.locator(".tag-picker__field").filter({ hasText: "函数" })).toBeVisible();
  await expect(page.getByText("未选择", { exact: true })).toHaveCount(0);
  await problemText.fill("求函数 $f(x)=x^2+1$ 的最小值。");
  await page.getByRole("button", { name: "图片附图" }).click();
  const figureStage = page.locator(".figure-cropper .image-selection-stage");
  const figureOverlay = figureStage.locator(".normalized-rect-editor");
  await expect(figureOverlay.locator(".normalized-rect-editor__selection")).toBeVisible();
  await expect(page.getByRole("button", { name: "自动适配" })).toBeVisible();
  await figureOverlay.scrollIntoViewIfNeeded();
  const overlayBox = await figureOverlay.boundingBox();
  if (!overlayBox) throw new Error("附图裁剪区域未完成布局");
  const drawTargetClass = await page.evaluate(({ x, y }) => (
    document.elementFromPoint(x, y)?.className || ""
  ), { x: overlayBox.x + overlayBox.width * 0.2, y: overlayBox.y + overlayBox.height * 0.2 });
  expect(String(drawTargetClass)).toContain("normalized-rect-editor__selection");
  const figureGeometry = await figureStage.evaluate((element) => {
    const bounds = (target: Element | null) => {
      const rect = target!.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    };
    return {
      stage: bounds(element),
      media: bounds(element.querySelector(".image-selection-stage__media")),
      editor: bounds(element.querySelector(".normalized-rect-editor")),
    };
  });
  expect(figureGeometry.media).toEqual(figureGeometry.stage);
  expect(figureGeometry.editor).toEqual(figureGeometry.stage);
  await page.mouse.move(overlayBox.x + overlayBox.width * 0.2, overlayBox.y + overlayBox.height * 0.2);
  await page.mouse.down();
  await page.mouse.move(overlayBox.x + overlayBox.width * 0.8, overlayBox.y + overlayBox.height * 0.75);
  await page.mouse.up();
  await expect(figureOverlay.locator(".normalized-rect-editor__selection")).toHaveAttribute("style", /left: 20/);
  await expect(page.getByText("未保存", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "保存修改" }).click();
  expect(task.problem.diagram_image_crop?.x).toBeCloseTo(0.2, 1);
  expect(task.problem.diagram_image_crop?.width).toBeCloseTo(0.6, 1);
  expect(task.problem.diagram_image_tone).toBe("auto");
  expect(task.problem.difficulty_coefficient_override).toBe(0.73);
  expect(task.problem.chapter).toBe("函数");
  expect(task.problem.section_question_count).toBe(8);
  await expect(page.getByRole("heading", { name: "题目与解答" })).toBeVisible();
  await expect(page.getByText("求函数", { exact: false })).toBeVisible();
  const readingLayout = await page.locator(".problem-content__lead.has-illustration").evaluate((element) => {
    const body = element.querySelector<HTMLElement>(".problem-content__body")!;
    const figure = element.querySelector<HTMLElement>(".problem-content__illustration")!;
    return {
      bodyHeight: body.getBoundingClientRect().height,
      figureHeight: figure.getBoundingClientRect().height,
      optionsInsideBody: Boolean(body.querySelector("[data-option-item='true']")),
    };
  });
  expect(readingLayout.optionsInsideBody).toBe(true);
  expect(Math.abs(readingLayout.figureHeight - readingLayout.bodyHeight * 2)).toBeLessThan(1);

  const layoutSamples = await page.locator(".problem-content__lead.has-illustration").evaluate(async (element) => {
    const figure = element.querySelector<HTMLElement>(".problem-content__illustration")!;
    const samples: string[] = [];
    for (let index = 0; index < 3; index += 1) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const rect = figure.getBoundingClientRect();
      samples.push(`${rect.width}:${rect.height}`);
    }
    return samples;
  });
  expect(new Set(layoutSamples).size).toBe(1);

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
