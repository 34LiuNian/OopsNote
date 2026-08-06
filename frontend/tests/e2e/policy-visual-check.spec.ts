import { expect, test } from "@playwright/test";

const selection = (channel_id: string, model_id: string) => ({ channel_id, model_id });

test.beforeEach(async ({ page }) => {
  await page.route("**/api/settings/ai/channels", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "vision-channel",
            version: 1,
            display_name: "阿里云百炼",
            provider: "openai-compatible",
            icon: "alibabacloud",
            base_url: "https://example.invalid/v1",
            enabled: true,
            has_secret: true,
            models: [{ id: "qwen3.7-flash", source: "阿里云百炼", enabled: true, capability: { tool_calling: true, vision: true }, discovered_at: null }],
            created_at: null,
            updated_at: null,
            secret_updated_at: null,
            policy_stages: ["vision", "diagram"],
          },
          {
            id: "agent-channel",
            version: 1,
            display_name: "Codex-Plus-0.06x-Wayapii",
            provider: "openai",
            icon: "openai",
            base_url: "https://example.invalid/v1",
            enabled: true,
            has_secret: true,
            models: [{ id: "gpt-5.6-luna", source: "Codex", enabled: true, capability: { tool_calling: true, vision: false }, discovered_at: null }],
            created_at: null,
            updated_at: null,
            secret_updated_at: null,
            policy_stages: ["agent", "review"],
          },
        ],
        policy: {
          version: 1,
          vision: selection("vision-channel", "qwen3.7-flash"),
          agent: selection("agent-channel", "gpt-5.6-luna"),
          review: selection("agent-channel", "gpt-5.6-luna"),
          diagram: selection("vision-channel", "qwen3.7-flash"),
          updated_at: "2026-08-06T02:38:43Z",
        },
      }),
    });
  });
});

test("policy topology and hover framing", async ({ page }) => {
  await page.goto("/settings/policy");
  const vision = page.getByRole("button", { name: /Vision \/ OCR/ });
  const agent = page.getByRole("button", { name: /^Agent/ });
  const review = page.getByRole("button", { name: /^Review/ });
  const diagram = page.getByRole("button", { name: /TikZ 题图重建/ });
  await expect(vision).toBeVisible();

  const [visionBox, agentBox, reviewBox, diagramBox] = await Promise.all([
    vision.boundingBox(), agent.boundingBox(), review.boundingBox(), diagram.boundingBox(),
  ]);
  expect(visionBox && agentBox && reviewBox && diagramBox).toBeTruthy();
  expect(agentBox!.x).toBeGreaterThan(visionBox!.x);
  expect(reviewBox!.x).toBeGreaterThan(agentBox!.x);
  expect(Math.abs(diagramBox!.x - agentBox!.x)).toBeLessThan(2);
  expect(diagramBox!.y).toBeGreaterThan(agentBox!.y + agentBox!.height);

  await agent.hover();
  await page.screenshot({ path: "C:/Users/75801/.codex/visualizations/2026/08/06/019fd658-eed7-76a1-8422-c30a602efe8a/policy-desktop-hover.png", fullPage: true });
});

test("policy topology remains readable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings/policy");
  await expect(page.getByRole("button", { name: /TikZ 题图重建/ })).toBeVisible();
  await page.screenshot({ path: "C:/Users/75801/.codex/visualizations/2026/08/06/019fd658-eed7-76a1-8422-c30a602efe8a/policy-mobile.png", fullPage: true });
});
