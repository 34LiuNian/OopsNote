import { expect, test } from "@playwright/test";
import { waitForAppReady } from "./app-ready";

test("diagram workbench keeps the full preview, details, and bounded text-only history", async ({ page }) => {
  const taskId = "diagram-workbench-ui-test";
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><rect width="120" height="80" fill="#fff"/><path d="M10 70H110M20 75V5" fill="none" stroke="#000" stroke-width="3"/></svg>';
  const candidates = Array.from({ length: 14 }, (_, index) => ({
    id: `candidate-${index + 1}`,
    ordinal: index + 1,
    parent_candidate_id: index ? `candidate-${index}` : null,
    source_kind: index === 13 ? "human" : "ai",
    tikz_source: "\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}",
    source_sha256: `sha-${index + 1}`,
    svg_path: `/assets/diagram-workbench-${index + 1}.svg`,
    pdf_path: `/assets/diagram-workbench-${index + 1}.pdf`,
    png_path: `/assets/diagram-workbench-${index + 1}.png`,
    renderer_profile_version: "test-v1",
    decision: index === 13 ? "accept" : "revise",
    hard_errors: [],
    soft_differences: [],
    review_reason: index === 13 ? "人工确认：保留横轴与磁场方向。" : `候选版本 ${index + 1} 的详细复核说明，内容较长用于验证详情不挤入历史列表。`,
    provider: index === 13 ? null : "google",
    model: index === 13 ? null : "test-model",
    run_id: `run-${index + 1}`,
    created_at: "2026-08-16T10:00:00+08:00",
  }));
  const task = {
    id: taskId,
    status: "completed",
    stage: "done",
    stage_message: "处理完成",
    created_at: "2026-08-16T10:00:00+08:00",
    updated_at: "2026-08-16T10:00:12+08:00",
    run: null,
    payload: {},
    asset: { asset_id: taskId, source: "upload", path: "/assets/diagram-workbench-source.png", mime_type: "image/png" },
    trace: null,
    problem: {
      problem_id: "problem-diagram-workbench",
      question_no: "1",
      question_type: "单选题",
      source: "界面测试.pdf",
      chapter: null,
      difficulty_coefficient_override: null,
      section_question_count: null,
      problem_text: "如图所示，求导线受力。",
      content_format: "oopsmark-v1",
      options: [{ key: "A", text: "正确" }],
      knowledge_tags: [],
      error_tags: [],
      user_tags: [],
      diagram_detected: true,
      diagram_enabled: true,
      diagram_kind: "tikz",
      diagram_tikz_source: candidates[13].tikz_source,
      diagram_svg: svg,
      diagram_image_path: null,
      diagram_image_tone: "auto",
      diagram_placement: { kind: "side", side: "right" },
      diagram_scale_adjustment_percent: 100,
      diagram_canvas_width_em: 12,
      diagram_canvas_height_em: 8,
      diagram_render_status: "ready",
      diagram_error: null,
      diagram_needs_review: false,
      diagram_items: [{
        id: "diagram-item-ui-test",
        ordinal: 0,
        source_asset_path: "/assets/diagram-workbench-source.png",
        source_region: null,
        fallback_image_path: null,
        image_tone: "auto",
        enabled: true,
        position: "right",
        placement: { kind: "side", side: "right" },
        scale_adjustment_percent: 100,
        status: "ready_tikz",
        selected_candidate_id: "candidate-14",
        candidates,
        active_run_id: null,
        needs_review: false,
        last_error: null,
        last_error_code: null,
        error_category: null,
      }],
    },
    solution: { problem_id: "problem-diagram-workbench", answer: "A", explanation: "受力平衡。" },
    tag: { problem_id: "problem-diagram-workbench", knowledge_points: [] },
  };

  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/auth/get-session*", async (route) => route.fulfill({
    json: {
      session: { id: "diagram-session", userId: "diagram-user" },
      user: { id: "diagram-user", name: "Diagram Test", email: "diagram@example.test", role: "admin" },
    },
  }));
  await page.route(new RegExp(`/api/(?:backend/)?tasks/${taskId}$`), async (route) => route.fulfill({ json: { task } }));
  await page.route(/\/api\/(?:backend\/)?settings\/tag-dimensions$/, async (route) => route.fulfill({ json: { dimensions: {} } }));
  await page.route(new RegExp(`/api/(?:backend/)?tasks/${taskId}/duplicates$`), async (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/assets/diagram-workbench-*.svg", async (route) => route.fulfill({ contentType: "image/svg+xml", body: svg }));
  await page.route("**/assets/diagram-workbench-source.png", async (route) => route.fulfill({ contentType: "image/png", body: "not-used" }));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`/tasks/${taskId}`, { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);
  await page.getByRole("button", { name: "编辑" }).click();
  await expect(page.getByText("编辑题目", { exact: true })).toBeVisible();

  const workbench = page.getByRole("region", { name: "附图工作台" });
  await expect(workbench.getByRole("button", { name: "折叠附图设置" })).toBeVisible();
  await workbench.getByRole("button", { name: "折叠附图设置" }).click();
  const collapsedPreview = workbench.getByRole("figure", { name: "折叠附图预览" });
  await expect(collapsedPreview).toBeVisible();
  await expect(collapsedPreview.locator("svg")).toBeVisible();
  expect((await collapsedPreview.boundingBox())?.height ?? 0).toBeGreaterThan(150);

  await workbench.getByRole("button", { name: "展开附图设置" }).click();
  const sidebar = workbench.getByRole("complementary", { name: "版本记录" });
  await expect(sidebar).toBeVisible();
  expect((await sidebar.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(230);
  await expect(sidebar.getByRole("button", { name: /^版本 \d+ ·/ })).toHaveCount(14);
  await expect(sidebar.locator("img")).toHaveCount(0);
  const historyList = sidebar.getByRole("group", { name: "版本历史列表" });
  const listStyle = await historyList.evaluate((element) => getComputedStyle(element).maxHeight);
  expect(listStyle).not.toBe("none");

  await expect(workbench.getByRole("region", { name: "版本详细信息" })).toContainText("人工确认");
  const preview = workbench.getByRole("figure", { name: "当前版本预览" });
  await expect(preview.locator("svg")).toBeVisible();
  await expect(preview.locator("svg path").first()).toHaveAttribute("stroke", "currentColor");
  await expect(preview.locator("svg rect").first()).toHaveAttribute("fill", "var(--oops-svg-background)");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(workbench).toBeVisible();
  const mobileHistorySize = await historyList.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  expect(mobileHistorySize.clientHeight).toBeLessThanOrEqual(300);
  expect(mobileHistorySize.scrollHeight).toBeGreaterThan(mobileHistorySize.clientHeight);
  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);
});
