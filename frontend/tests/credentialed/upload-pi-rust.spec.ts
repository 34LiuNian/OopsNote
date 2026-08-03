import { existsSync } from "node:fs";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { waitForAppReady } from "../e2e/app-ready";

const imagePath = process.env.OOPSNOTE_CREDENTIALED_E2E_IMAGE!;
const expectDiagram = process.env.OOPSNOTE_CREDENTIALED_E2E_EXPECT_DIAGRAM === "1";
const expectedStages = [
  "queued",
  "starting",
  "ocr",
  "solving",
  "verifying",
  "tagging",
  "finalizing",
] as const;

type TaskView = {
  task: {
    id: string;
    status: "pending" | "processing" | "completed" | "failed" | "cancelled";
    stage?: string | null;
    stage_message?: string | null;
    active_run_id?: string | null;
    problem?: {
      content_format?: string | null;
      problem_text?: string | null;
      has_diagram?: boolean;
    } | null;
    solution?: {
      answer?: string | null;
      explanation?: string | null;
    } | null;
    run?: {
      status: string;
      error_code?: string | null;
      error_message?: string | null;
      stages: Array<{ stage: string; status: string }>;
    } | null;
  };
};

async function readTask(request: APIRequestContext, taskId: string): Promise<TaskView> {
  const response = await request.get(`/api/tasks/${encodeURIComponent(taskId)}`);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json() as Promise<TaskView>;
}

test("real upload reaches Pi-rust finalize and renders the persisted OopsMark result", async ({ page, request }) => {
  expect(existsSync(imagePath), `Credentialed E2E image does not exist: ${imagePath}`).toBeTruthy();

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const uploadResponsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && response.url().includes("/api/upload?auto_process=false")
  ));
  const enqueueResponsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && /\/api\/tasks\/[^/]+\/process\?background=true$/.test(response.url())
  ));

  await page.locator('input[type="file"][accept="image/*"]').setInputFiles(imagePath);
  await expect(page.getByText("待处理 1 / 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "提交并入队" }).click();

  const uploadResponse = await uploadResponsePromise;
  expect(uploadResponse.ok(), await uploadResponse.text()).toBeTruthy();
  const created = await uploadResponse.json() as TaskView;
  const taskId = created.task.id;
  expect(taskId).toBeTruthy();

  const enqueueResponse = await enqueueResponsePromise;
  expect(enqueueResponse.ok(), await enqueueResponse.text()).toBeTruthy();
  await expect(page.getByText("已加入队列", { exact: true })).toBeVisible();

  await page.goto(`/tasks/${taskId}`, { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  let latest: TaskView | null = null;
  await expect.poll(async () => {
    latest = await readTask(request, taskId);
    const task = latest.task;
    if (task.status === "failed" || task.status === "cancelled") {
      const evidence = {
        task_id: task.id,
        status: task.status,
        stage: task.stage,
        stage_message: task.stage_message,
        run_status: task.run?.status,
        error_code: task.run?.error_code,
        error_message: task.run?.error_message,
      };
      throw new Error(`Credentialed task terminated before finalize: ${JSON.stringify(evidence)}`);
    }
    return task.status;
  }, {
    message: `waiting for credentialed task ${taskId} to complete`,
    timeout: 10 * 60_000,
    intervals: [1_000, 2_000, 3_000, 5_000],
  }).toBe("completed");

  const task = latest!.task;
  expect(task.active_run_id).toBeNull();
  expect(task.run?.status).toBe("completed");
  expect(task.run?.stages.map((stage) => stage.stage)).toEqual(expectedStages);
  expect(task.run?.stages.every((stage) => stage.status === "completed")).toBeTruthy();
  expect(task.problem?.content_format).toBe("oopsmark-v1");
  expect(task.problem?.problem_text?.trim()).toBeTruthy();
  if (expectDiagram) {
    expect(task.problem?.has_diagram).toBe(true);
  }
  expect(task.solution?.answer?.trim()).toBeTruthy();
  expect(task.solution?.explanation?.trim()).toBeTruthy();

  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForAppReady(page);
  await expect(page.getByRole("button", { name: /5\/5 阶段完成/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "题目与解答" })).toBeVisible();
  await expect(page.getByText("尚未解析出题目", { exact: true })).toHaveCount(0);
});
