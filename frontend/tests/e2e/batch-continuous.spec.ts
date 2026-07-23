import { expect, test, type Page } from "@playwright/test";

function createPdf(pageCount: number): Buffer {
  const objects: string[] = [];
  const pageRefs = Array.from({ length: pageCount }, (_, index) => `${3 + index * 2} 0 R`).join(" ");
  objects.push("<< /Type /Catalog /Pages 2 0 R >>");
  objects.push(`<< /Type /Pages /Kids [${pageRefs}] /Count ${pageCount} >>`);
  for (let index = 0; index < pageCount; index += 1) {
    const pageObject = 3 + index * 2;
    const contentObject = pageObject + 1;
    const content = "0.97 g 0 0 600 800 re f\n0 G 1 w 36 36 528 728 re S\n";
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << >> /Contents ${contentObject} 0 R >>`);
    objects.push(`<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}endstream`);
  }
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf);
}

async function openWorkspace(page: Page, options: { failPatchCount?: number } = {}) {
  let failedPatches = 0;
  let session = {
    file_hash: "fixture",
    filename: "continuous.pdf",
    mime_type: "application/pdf",
    asset_path: "/assets/batch-fixture.pdf",
    page_count: 3,
    subject: "auto",
    notes: "",
    active_page: 0,
    crop_rect: { x: 0, y: 0, width: 1, height: 1 },
    crop_confirmed: false,
    segments: [] as unknown[],
    created_at: "2026-07-23T00:00:00Z",
    updated_at: "2026-07-23T00:00:00Z",
  };
  await page.route(/\/batch-sessions(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "GET" && pathname.endsWith("/batch-sessions")) {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    if (request.method() === "GET") {
      await route.fulfill({ status: 404, json: { detail: "not found" } });
      return;
    }
    if (request.method() === "PATCH") {
      if (failedPatches < (options.failPatchCount ?? 0)) {
        failedPatches += 1;
        await route.fulfill({ status: 503, body: "temporary save failure" });
        return;
      }
      session = { ...session, ...(request.postDataJSON() as Partial<typeof session>) };
    }
    await route.fulfill({ json: { session } });
  });
  await page.goto("/batch-segment", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();
  await page.locator('input[type="file"]').setInputFiles({ name: "continuous.pdf", mimeType: "application/pdf", buffer: createPdf(3) });
  await expect(page.locator(".batch-crop-editor")).toBeVisible();
  await expect(page.locator(".batch-page-rail nav button")).toHaveCount(3);
}

test("one crop produces a lazy, single-column, gapless selection surface", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openWorkspace(page);
  const editor = (await page.locator(".batch-crop-editor").boundingBox())!;
  await page.mouse.move(editor.x + editor.width * 0.08, editor.y + editor.height * 0.08);
  await page.mouse.down();
  await page.mouse.move(editor.x + editor.width * 0.92, editor.y + editor.height * 0.9, { steps: 8 });
  await page.mouse.up();
  await page.getByRole("button", { name: "检查裁剪" }).click();
  const pages = page.locator(".batch-continuous-page");
  await expect(pages).toHaveCount(3);
  const pageGeometry = await pages.evaluateAll((elements) => elements.map((element) => {
    const bounds = element.getBoundingClientRect();
    return { top: bounds.top, bottom: bounds.bottom, width: bounds.width };
  }));
  expect(Math.abs(pageGeometry[0].bottom - pageGeometry[1].top)).toBeLessThan(1.5);
  expect(Math.abs(pageGeometry[0].width - pageGeometry[1].width)).toBeLessThan(1);
  await page.getByRole("button", { name: /确认裁剪并开始框题/ }).click();

  const surface = (await page.getByTestId("batch-continuous-surface").boundingBox())!;
  await page.locator(".batch-document-viewport").evaluate((element) => {
    element.scrollTop = Math.max(0, element.querySelector<HTMLElement>(".batch-continuous-page")!.offsetHeight - 320);
  });
  const firstAfter = (await pages.nth(0).boundingBox())!;
  await page.mouse.move(surface.x + surface.width * 0.2, firstAfter.y + firstAfter.height - 60);
  await page.mouse.down();
  await page.mouse.move(surface.x + surface.width * 0.72, firstAfter.y + firstAfter.height + 90, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);
  await expect(page.locator(".batch-selection-handle")).toHaveCount(8);
  await expect(page.locator(".batch-selection-list > button")).toHaveCount(1);
  await expect(page.locator(".batch-scan-layout.is-spread")).toHaveCount(0);
});

test("viewer zoom uses Ctrl+wheel and page navigation has no previous/next controls", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await openWorkspace(page);
  await page.getByRole("button", { name: "检查裁剪" }).click();
  await page.getByRole("button", { name: /确认裁剪并开始框题/ }).click();
  await expect(page.getByRole("button", { name: "上一页" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下一页" })).toHaveCount(0);
  const before = await page.locator(".batch-pdf-controls > span").first().textContent();
  const viewport = (await page.locator(".batch-document-viewport").boundingBox())!;
  await page.keyboard.down("Control");
  await page.mouse.move(viewport.x + viewport.width / 2, viewport.y + 180);
  await page.mouse.wheel(0, -100);
  await page.keyboard.up("Control");
  await expect(page.locator(".batch-pdf-controls > span").first()).not.toHaveText(before ?? "100%");
});

test("compact workspace removes the app shell and keeps the document controls usable", async ({ page }) => {
  await page.setViewportSize({ width: 700, height: 760 });
  await openWorkspace(page);
  await page.getByRole("button", { name: "检查裁剪" }).click();
  await page.getByRole("button", { name: /确认裁剪并开始框题/ }).click();
  await expect(page.locator(".app-sidebar")).toBeHidden();
  await expect(page.locator(".batch-page-rail")).toBeHidden();
  await expect(page.locator(".batch-selection-rail")).toBeVisible();
  const controls = (await page.locator(".batch-pdf-controls").boundingBox())!;
  expect(controls.x).toBeGreaterThanOrEqual(0);
  expect(controls.x + controls.width).toBeLessThanOrEqual(701);
  await expect(page.getByRole("button", { name: "适合宽度" })).toBeVisible();
});

test("autosave reports a transient failure and retries without blocking the workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 });
  await openWorkspace(page, { failPatchCount: 1 });
  await expect(page.locator(".batch-save-state")).toHaveText("保存失败，正在重试", { timeout: 15_000 });
  await expect(page.locator(".batch-save-state")).toHaveText("已保存", { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "检查裁剪" })).toBeEnabled();
});
