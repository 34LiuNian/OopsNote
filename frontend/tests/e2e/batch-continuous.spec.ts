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

async function openWorkspace(page: Page, options: {
  failPatchCount?: number;
  cropRect?: { x: number; y: number; width: number; height: number };
  dropColumnLayoutPatch?: boolean;
  onPatch?: (payload: Record<string, unknown>) => void;
  onProcess?: () => void;
} = {}) {
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
    crop_rect: options.cropRect ?? { x: 0, y: 0, width: 1, height: 1 },
    crop_confirmed: false,
    column_layout: { column_count: 1, overlap_ratio: 0.5 },
    excluded_page_indices: [] as number[],
    segments: [] as unknown[],
    revision: 0,
    created_at: "2026-07-23T00:00:00Z",
    updated_at: "2026-07-23T00:00:00Z",
  };
  await page.route(/\/batch-sessions(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && pathname.endsWith("/process")) {
      options.onProcess?.();
      const command = request.postDataJSON() as { expected_revision: number };
      if (command.expected_revision !== session.revision) {
        await route.fulfill({ status: 409, json: { detail: "revision conflict" } });
        return;
      }
      const pending = (session.segments as Array<Record<string, unknown>>)
        .filter((segment) => segment.status === "pending");
      const items = pending.map((segment, index) => ({
        segment_id: segment.id,
        question_no: segment.question_no,
        task_id: `task-${index + 1}`,
        run_id: `run-${index + 1}`,
        status: "processing",
        error: null,
      }));
      session = {
        ...session,
        revision: session.revision + 1,
        segments: (session.segments as Array<Record<string, unknown>>).map((segment, index) => segment.status === "pending"
          ? { ...segment, status: "processing", task_id: `task-${index + 1}` }
          : segment),
      };
      await route.fulfill({ json: {
        requested: pending.length,
        created: pending.length,
        queued: pending.length,
        failed: 0,
        items,
        session,
      } });
      return;
    }
    if (request.method() === "GET" && pathname.endsWith("/batch-sessions")) {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    if (request.method() === "GET") {
      if (options.cropRect) {
        await route.fulfill({ json: { session } });
        return;
      }
      await route.fulfill({ status: 404, json: { detail: "not found" } });
      return;
    }
    if (request.method() === "PATCH") {
      const patch = request.postDataJSON() as Record<string, unknown>;
      options.onPatch?.(patch);
      if (failedPatches < (options.failPatchCount ?? 0)) {
        failedPatches += 1;
        await route.fulfill({ status: 503, body: "temporary save failure" });
        return;
      }
      if (patch.expected_revision !== session.revision) {
        await route.fulfill({ status: 409, json: { detail: "revision conflict" } });
        return;
      }
      delete patch.expected_revision;
      if (options.dropColumnLayoutPatch) delete patch.column_layout;
      session = { ...session, ...(patch as Partial<typeof session>), revision: session.revision + 1 };
    }
    await route.fulfill({ json: { session } });
  });
  await page.goto("/batch-segment", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();
  await page.locator('input[type="file"]').setInputFiles({ name: "continuous.pdf", mimeType: "application/pdf", buffer: createPdf(3) });
  await expect(page.locator(".batch-crop-editor")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".batch-page-rail__page")).toHaveCount(3);
  await expect(page.locator(".batch-page-rail__page small")).toHaveCount(0);
}

test("recent files expose delete directly without a secondary menu", async ({ page }) => {
  await page.route(/\/batch-sessions$/, async (route) => {
    await route.fulfill({ json: { items: [{
      file_hash: "recent-fixture",
      filename: "recent.pdf",
      mime_type: "application/pdf",
      asset_path: "/assets/recent.pdf",
      page_count: 2,
      subject: "auto",
      notes: "",
      active_page: 0,
      crop_rect: { x: 0, y: 0, width: 1, height: 1 },
      crop_confirmed: false,
      column_layout: { column_count: 2, overlap_ratio: 0.5 },
      excluded_page_indices: [],
      segments: [],
      revision: 0,
      created_at: "2026-07-23T00:00:00Z",
      updated_at: "2026-07-23T00:00:00Z",
    }] } });
  });
  await page.goto("/batch-segment", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#oops-splash")).toBeHidden();
  await expect(page.getByRole("button", { name: "删除最近文件" })).toBeVisible();
  await expect(page.locator(".batch-history-menu, .batch-scan-history details")).toHaveCount(0);
  await expect(page.locator(".batch-scan-history__meta")).toContainText("2 栏");
});

test("restored workspace stays clean until persisted content changes and saves its column layout", async ({ page }) => {
  let patchCount = 0;
  let lastPatch: Record<string, unknown> | undefined;
  await openWorkspace(page, {
    cropRect: { x: 0, y: 0, width: 1, height: 1 },
    onPatch: (payload) => {
      patchCount += 1;
      lastPatch = payload;
    },
  });

  await expect(page.locator(".batch-save-state")).toHaveClass(/is-saved/);
  await page.locator(".batch-page-rail__page").nth(1).click();
  await page.waitForTimeout(900);
  expect(patchCount).toBe(0);

  await page.getByRole("combobox", { name: "分栏数量" }).selectOption("2");
  await expect.poll(() => patchCount).toBe(1);
  expect(lastPatch?.column_layout).toEqual({ column_count: 2, overlap_ratio: 0.5 });
  await expect(page.locator(".batch-save-state")).toHaveClass(/is-saved/);
  await page.waitForTimeout(900);
  expect(patchCount).toBe(1);
  await page.locator(".batch-workflow-toolbar button").first().click();
  await expect(page.locator(".batch-scan-history__meta")).toContainText("2 栏");
});

test("autosave rejects a backend response that drops the column layout", async ({ page }) => {
  await openWorkspace(page, {
    cropRect: { x: 0, y: 0, width: 1, height: 1 },
    dropColumnLayoutPatch: true,
  });
  await page.getByRole("combobox", { name: "分栏数量" }).selectOption("2");
  await expect(page.locator(".batch-save-state")).toHaveClass(/is-failed/, { timeout: 15_000 });
});

test("uniform crop rejects undersized regions and compacts resize handles", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await openWorkspace(page, { cropRect: { x: 0.1, y: 0.1, width: 0.04, height: 0.04 } });
  await expect(page.getByRole("button", { name: "检查裁剪与分栏" })).toBeDisabled();
  await expect(page.locator(".normalized-crop-overlay__rect .normalized-crop-handle.is-n")).toBeHidden();
  await expect(page.locator(".normalized-crop-overlay__rect .normalized-crop-handle.is-e")).toBeHidden();
  await expect(page.locator(".normalized-crop-overlay__rect .normalized-crop-handle.is-se")).toBeVisible();
});

test("crop setup shows equal column guides and previews half-neighbor reading units", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openWorkspace(page);
  const pdfDarkToggle = page.getByRole("button", { name: "切换 PDF 暗色预览" });
  await expect(pdfDarkToggle).toBeVisible();
  await expect(pdfDarkToggle).toHaveAttribute("aria-pressed", "false");
  await pdfDarkToggle.click();
  await expect(page.locator(".batch-crop-editor")).toHaveClass(/is-inverted/);
  await expect(pdfDarkToggle).toHaveAttribute("aria-pressed", "true");
  await pdfDarkToggle.click();
  await expect(page.locator(".batch-crop-editor")).not.toHaveClass(/is-inverted/);
  await page.getByRole("combobox", { name: "分栏数量" }).selectOption("2");

  const guide = page.locator(".normalized-crop-overlay__column-guide");
  await expect(guide).toHaveCount(1);
  const guideLeft = await guide.evaluate((element) => Number.parseFloat(getComputedStyle(element).left));
  const cropWidth = await page.locator(".normalized-crop-overlay__rect").evaluate((element) => element.getBoundingClientRect().width);
  expect(guideLeft / cropWidth).toBeCloseTo(0.5, 1);

  const cropHandleColor = await page.locator(".normalized-crop-overlay__rect .normalized-crop-handle.is-nw").evaluate(
    (element) => getComputedStyle(element, "::before").borderTopColor,
  );
  expect(cropHandleColor).toBe("rgb(14, 165, 233)");
  const cropStrokeGeometry = await page.locator(".normalized-crop-overlay__rect").evaluate((element) => {
    const frameRect = element.getBoundingClientRect();
    const handleRect = element.querySelector(".normalized-crop-handle.is-nw")!.getBoundingClientRect();
    return {
      frame: Number.parseFloat(getComputedStyle(element).getPropertyValue("--crop-frame-stroke")),
      handleInside: handleRect.left >= frameRect.left && handleRect.top >= frameRect.top,
      editorShadow: getComputedStyle(element.closest(".batch-crop-editor")!).boxShadow,
    };
  });
  expect(cropStrokeGeometry.frame).toBeGreaterThan(0);
  expect(cropStrokeGeometry.handleInside).toBe(true);
  expect(cropStrokeGeometry.editorShadow).toBe("none");

  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  const units = page.locator(".batch-continuous-page");
  await expect(units).toHaveCount(6);
  await expect(units.nth(0)).toHaveAttribute("data-page-index", "0");
  await expect(units.nth(0)).toHaveAttribute("data-column-index", "0");
  await expect(units.nth(1)).toHaveAttribute("data-page-index", "0");
  await expect(units.nth(1)).toHaveAttribute("data-column-index", "1");
  await expect(page.getByTestId("batch-continuous-surface")).toHaveClass(/is-column-layout/);
  await expect(units.nth(0).locator(".batch-continuous-page__borrow-mask.is-left")).toHaveCount(0);
  await expect(units.nth(0).locator(".batch-continuous-page__borrow-mask.is-right")).toHaveCount(1);
  await expect(units.nth(1).locator(".batch-continuous-page__borrow-mask.is-left")).toHaveCount(1);
  await expect(units.nth(1).locator(".batch-continuous-page__borrow-mask.is-right")).toHaveCount(0);
  await expect(units.nth(0)).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  const rightBorrowMask = units.nth(0).locator(".batch-continuous-page__borrow-mask.is-right");
  const borrowMaskStyles = await rightBorrowMask.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    blur: getComputedStyle(element).backdropFilter,
  }));
  expect(borrowMaskStyles.background).toBe("rgba(0, 0, 0, 0)");
  expect(borrowMaskStyles.blur).toContain("blur(1.4px)");
  const rightBorrowBounds = (await rightBorrowMask.boundingBox())!;
  await page.mouse.move(rightBorrowBounds.x + rightBorrowBounds.width / 2, rightBorrowBounds.y + rightBorrowBounds.height / 2);
  await expect(rightBorrowMask).toHaveClass(/is-hovered/);
  await expect(rightBorrowMask).toHaveCSS("opacity", "0");

  const contentGeometry = await units.evaluateAll((elements) => elements.slice(0, 2).map((element) => {
    const pageBounds = element.getBoundingClientRect();
    const contentBounds = element.querySelector<HTMLElement>(".batch-continuous-page__content")!.getBoundingClientRect();
    return {
      left: (contentBounds.left - pageBounds.left) / pageBounds.width,
      width: contentBounds.width / pageBounds.width,
    };
  }));
  expect(contentGeometry[0].left).toBeCloseTo(0.25, 2);
  expect(contentGeometry[0].width).toBeCloseTo(0.75, 2);
  expect(contentGeometry[1].left).toBeCloseTo(0, 2);
  expect(contentGeometry[1].width).toBeCloseTo(0.75, 2);

  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();
  const viewport = page.locator(".batch-document-viewport");
  await viewport.evaluate((element) => {
    const first = element.querySelector<HTMLElement>('.batch-continuous-page[data-page-index="0"][data-column-index="0"]')!;
    element.scrollTop = Math.max(0, first.offsetHeight - 300);
  });
  const surface = (await page.getByTestId("batch-continuous-surface").boundingBox())!;
  const firstColumn = (await units.nth(0).boundingBox())!;
  await page.mouse.move(surface.x + surface.width * 0.35, firstColumn.y + firstColumn.height - 60);
  await page.mouse.down();
  await page.mouse.move(surface.x + surface.width * 0.65, firstColumn.y + firstColumn.height + 90, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);
});

test("a source page can be deleted and restored without renumbering remaining selections", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openWorkspace(page);
  await expect(page.locator(".batch-page-rail__item.is-active")).toHaveCount(1);
  await expect(page.locator('.batch-page-rail__item.is-active [aria-current="page"]')).toHaveCount(1);
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();

  const viewport = page.locator(".batch-document-viewport");
  await viewport.evaluate((element) => {
    const third = element.querySelector<HTMLElement>('.batch-continuous-page[data-page-index="2"]')!;
    element.scrollTop = third.offsetTop;
  });
  const thirdPage = (await page.locator('.batch-continuous-page[data-page-index="2"]').boundingBox())!;
  await page.mouse.move(thirdPage.x + thirdPage.width * 0.25, thirdPage.y + 80);
  await page.mouse.down();
  await page.mouse.move(thirdPage.x + thirdPage.width * 0.7, thirdPage.y + 230, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);

  await page.getByRole("button", { name: "删除第 1 页" }).click();
  await expect(page.locator(".batch-continuous-page")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "第 1 页，已删除" })).toBeDisabled();
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);
  await expect(page.locator(".batch-selection-list__item")).toContainText("第 3 页");

  await page.getByRole("button", { name: "恢复第 1 页" }).click();
  await expect(page.locator(".batch-continuous-page")).toHaveCount(3);
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "删除第 1 页" })).toBeVisible();
});

test("submit starts the persisted batch with one backend process request", async ({ page }) => {
  let processCalls = 0;
  let legacyUploadCalls = 0;
  await page.route(/\/upload(?:\?.*)?$/, async (route) => {
    legacyUploadCalls += 1;
    await route.fulfill({ status: 500, body: "legacy upload must not be called" });
  });
  await openWorkspace(page, { onProcess: () => { processCalls += 1; } });
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();
  const firstPage = (await page.locator('.batch-continuous-page[data-page-index="0"]').boundingBox())!;
  await page.mouse.move(firstPage.x + 80, firstPage.y + 80);
  await page.mouse.down();
  await page.mouse.move(firstPage.x + firstPage.width - 80, firstPage.y + 260, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator("[data-selection-id]")).toHaveCount(1);
  await expect(page.locator(".batch-save-state")).toHaveText("已保存", { timeout: 15_000 });

  await page.getByRole("button", { name: "提交 1 道题目" }).click();

  await expect.poll(() => processCalls).toBe(1);
  expect(legacyUploadCalls).toBe(0);
  await expect(page.locator(".batch-selection-list__item")).toContainText("处理中");
  const processingFrame = page.locator(".batch-selection.is-processing");
  await expect(processingFrame).toHaveCount(1);
  const marqueeStyles = await processingFrame.evaluate((element) => {
    const styles = getComputedStyle(element, "::before");
    return {
      animationDuration: styles.animationDuration,
      animationName: styles.animationName,
      backgroundImage: styles.backgroundImage,
    };
  });
  expect(marqueeStyles.animationName).toContain("batch-selection-marquee");
  expect(marqueeStyles.animationDuration).toBe("1.8s");
  expect(marqueeStyles.backgroundImage).toContain("conic-gradient");
});

test("submitted segments remain counted in recent files and reopen intact", async ({ page }) => {
  await page.route(/\/api\/assets\/batch-fixture\.pdf$/, async (route) => {
    await route.fulfill({
      contentType: "application/pdf",
      body: createPdf(3),
    });
  });
  await openWorkspace(page);
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();
  const firstPage = (await page.locator('.batch-continuous-page[data-page-index="0"]').boundingBox())!;
  await page.mouse.move(firstPage.x + 80, firstPage.y + 80);
  await page.mouse.down();
  await page.mouse.move(firstPage.x + firstPage.width - 80, firstPage.y + 260, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator(".batch-save-state")).toHaveText("已保存", { timeout: 15_000 });
  await page.getByRole("button", { name: "提交 1 道题目" }).click();
  await expect(page.locator(".batch-selection-list__item")).toContainText("处理中");

  await page.getByRole("button", { name: "返回最近文件" }).click();
  const recent = page.locator(".batch-scan-history__item").filter({ hasText: "continuous.pdf" });
  await expect(recent).toContainText("1 道");
  await expect(recent).toContainText("1 进行中");
  await recent.getByRole("button", { name: "查看" }).click();

  await expect(page.locator(".batch-selection-list__item")).toHaveCount(1);
  await expect(page.locator(".batch-selection-list__item")).toContainText("处理中");
});

test("viewer follows live color scheme and can scroll fully above the bottom safe area", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.setViewportSize({ width: 1200, height: 700 });
  await openWorkspace(page);
  const editor = page.locator(".batch-crop-editor");
  const workspace = page.locator(".batch-continuous-workspace");
  const controls = page.locator(".batch-pdf-controls");
  const pageInput = page.locator(".batch-page-input input");

  await expect(editor).not.toHaveClass(/is-inverted/);
  await expect(workspace).toHaveCSS("background-color", "rgb(228, 228, 231)");
  await expect(controls).toHaveCSS("background-color", "rgb(244, 244, 245)");
  await expect(pageInput).toHaveCSS("background-color", "rgb(255, 255, 255)");

  await page.emulateMedia({ colorScheme: "dark" });
  await expect(editor).toHaveClass(/is-inverted/);
  await expect(workspace).toHaveCSS("background-color", "rgb(32, 33, 36)");
  await expect(controls).toHaveCSS("background-color", "rgb(42, 44, 48)");
  await expect(pageInput).toHaveCSS("background-color", "rgb(31, 32, 35)");
  const darkStyles = await editor.evaluate((element) => {
    const image = element.querySelector("img");
    const overlay = element.querySelector<HTMLElement>(".normalized-crop-overlay__rect");
    return {
      background: getComputedStyle(element).backgroundColor,
      imageFilter: image ? getComputedStyle(image).filter : "",
      overlayShadow: overlay ? getComputedStyle(overlay).boxShadow : "",
    };
  });
  expect(darkStyles.background).toBe("rgb(5, 5, 5)");
  expect(darkStyles.imageFilter).toContain("invert(1)");
  expect(darkStyles.overlayShadow).toContain("rgba(255, 255, 255, 0.16)");

  await page.emulateMedia({ colorScheme: "light" });
  await expect(editor).not.toHaveClass(/is-inverted/);
  await expect(workspace).toHaveCSS("background-color", "rgb(228, 228, 231)");

  const viewport = page.locator(".batch-document-viewport");
  await viewport.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  const bottomGeometry = await viewport.evaluate((element) => {
    const editorElement = element.querySelector<HTMLElement>(".batch-crop-editor")!;
    const viewportBounds = element.getBoundingClientRect();
    const editorBounds = editorElement.getBoundingClientRect();
    return {
      remainingScroll: element.scrollHeight - element.clientHeight - element.scrollTop,
      visibleBottomSpace: viewportBounds.bottom - editorBounds.bottom,
    };
  });
  expect(bottomGeometry.remainingScroll).toBeLessThanOrEqual(1);
  expect(bottomGeometry.visibleBottomSpace).toBeGreaterThanOrEqual(64);
});

test("one crop produces a lazy, single-column, gapless selection surface", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openWorkspace(page);
  const editor = (await page.locator(".batch-crop-editor").boundingBox())!;
  await page.mouse.move(editor.x + editor.width * 0.08, editor.y + editor.height * 0.08);
  await page.mouse.down();
  await page.mouse.move(editor.x + editor.width * 0.92, editor.y + editor.height * 0.9, { steps: 8 });
  await page.mouse.up();
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  const pages = page.locator(".batch-continuous-page");
  await expect(pages).toHaveCount(3);
  const pageGeometry = await pages.evaluateAll((elements) => elements.map((element) => {
    const bounds = element.getBoundingClientRect();
    return { top: bounds.top, bottom: bounds.bottom, width: bounds.width };
  }));
  expect(Math.abs(pageGeometry[0].bottom - pageGeometry[1].top)).toBeLessThan(1.5);
  expect(Math.abs(pageGeometry[0].width - pageGeometry[1].width)).toBeLessThan(1);
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();

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
  const selectionStyle = await page.locator("[data-selection-id]").evaluate((element) => {
    const style = getComputedStyle(element);
    return { frameStroke: style.getPropertyValue("--batch-selection-stroke"), borderRadius: style.borderTopLeftRadius };
  });
  expect(selectionStyle).toEqual({ frameStroke: "2px", borderRadius: "5px" });
  const handleAlignment = await page.locator("[data-selection-id]").evaluate((element) => {
    const selection = element.getBoundingClientRect();
    const border = Number.parseFloat(getComputedStyle(element).getPropertyValue("--batch-selection-stroke"));
    const rect = (name: string) => element.querySelector<HTMLElement>(`.batch-selection-handle.is-${name}`)!.getBoundingClientRect();
    const n = rect("n");
    const e = rect("e");
    const se = rect("se");
    return {
      northCenterOffset: Math.abs(n.top + n.height / 2 - (selection.top + border / 2)),
      eastCenterOffset: Math.abs(e.left + e.width / 2 - (selection.right - border / 2)),
      southEastXOffset: Math.abs(se.left + se.width / 2 - (selection.right - border / 2)),
      southEastYOffset: Math.abs(se.top + se.height / 2 - (selection.bottom - border / 2)),
      northRadius: getComputedStyle(element.querySelector<HTMLElement>(".batch-selection-handle.is-n")!, "::before").borderRadius,
    };
  });
  expect(handleAlignment.northCenterOffset).toBeLessThanOrEqual(0.5);
  expect(handleAlignment.eastCenterOffset).toBeLessThanOrEqual(0.5);
  expect(handleAlignment.southEastXOffset).toBeLessThanOrEqual(0.5);
  expect(handleAlignment.southEastYOffset).toBeLessThanOrEqual(0.5);
  expect(handleAlignment.northRadius).toBe("999px");
  const baseHandleStyle = await page.locator("[data-selection-id]").evaluate((element) => {
    const north = element.querySelector<HTMLElement>(".batch-selection-handle.is-n")!;
    const northWest = element.querySelector<HTMLElement>(".batch-selection-handle.is-nw")!;
    return {
      frameStroke: Number.parseFloat(getComputedStyle(element).getPropertyValue("--batch-selection-stroke")),
      sideLength: Number.parseFloat(getComputedStyle(north, "::before").width),
      cornerStroke: Number.parseFloat(getComputedStyle(northWest, "::before").paddingTop),
      cornerRadius: Number.parseFloat(getComputedStyle(northWest, "::before").borderTopLeftRadius),
    };
  });
  await page.getByRole("button", { name: "放大" }).click();
  const enlargedHandleStyle = await page.locator("[data-selection-id]").evaluate((element) => {
    const north = element.querySelector<HTMLElement>(".batch-selection-handle.is-n")!;
    const northWest = element.querySelector<HTMLElement>(".batch-selection-handle.is-nw")!;
    return {
      frameStroke: Number.parseFloat(getComputedStyle(element).getPropertyValue("--batch-selection-stroke")),
      sideLength: Number.parseFloat(getComputedStyle(north, "::before").width),
      cornerStroke: Number.parseFloat(getComputedStyle(northWest, "::before").paddingTop),
      cornerRadius: Number.parseFloat(getComputedStyle(northWest, "::before").borderTopLeftRadius),
    };
  });
  expect(enlargedHandleStyle.frameStroke / baseHandleStyle.frameStroke).toBeCloseTo(1.1, 1);
  expect(enlargedHandleStyle.sideLength / baseHandleStyle.sideLength).toBeCloseTo(1.1, 1);
  expect(enlargedHandleStyle.cornerStroke / baseHandleStyle.cornerStroke).toBeCloseTo(1.1, 1);
  expect(enlargedHandleStyle.cornerRadius / baseHandleStyle.cornerRadius).toBeCloseTo(1.1, 1);
  await expect(page.locator(".batch-selection-list__item")).toHaveCount(1);
  await expect(page.locator(".batch-selection-list__item button button")).toHaveCount(0);
  await expect(page.locator(".batch-scan-layout.is-spread")).toHaveCount(0);

  const review = page.getByRole("combobox", { name: "第 1 题异常状态" });
  await review.selectOption("multiple_questions");
  await expect(page.locator("[data-selection-id]")).toHaveClass(/is-needs_review/);
  await expect(page.locator(".batch-selection-list__item")).toContainText("包含多道完整题目");
  await review.selectOption("");
  await expect(page.locator("[data-selection-id]")).not.toHaveClass(/is-needs_review/);
});

test("viewer zoom uses Ctrl+wheel and page navigation has no previous/next controls", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await openWorkspace(page);
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();
  await expect(page.getByRole("button", { name: "上一页" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下一页" })).toHaveCount(0);
  const before = await page.locator(".batch-pdf-controls > span").first().textContent();
  const viewportLocator = page.locator(".batch-document-viewport");
  await viewportLocator.evaluate((element) => {
    const state = window as typeof window & { __viewerWheelPrevented?: boolean };
    state.__viewerWheelPrevented = false;
    element.addEventListener("wheel", (event) => { state.__viewerWheelPrevented = event.defaultPrevented; }, { once: true });
  });
  const pageScaleBefore = await page.evaluate(() => ({ innerWidth: window.innerWidth, dpr: window.devicePixelRatio }));
  const viewport = (await viewportLocator.boundingBox())!;
  await page.keyboard.down("Control");
  await page.mouse.move(viewport.x + viewport.width / 2, viewport.y + 180);
  await page.mouse.wheel(0, -100);
  await page.keyboard.up("Control");
  await expect(page.locator(".batch-pdf-controls > span").first()).not.toHaveText(before ?? "100%");
  const wheelResult = await page.evaluate(() => ({
    prevented: (window as typeof window & { __viewerWheelPrevented?: boolean }).__viewerWheelPrevented,
    innerWidth: window.innerWidth,
    dpr: window.devicePixelRatio,
  }));
  expect(wheelResult.prevented).toBe(true);
  expect({ innerWidth: wheelResult.innerWidth, dpr: wheelResult.dpr }).toEqual(pageScaleBefore);
});

test("compact workspace removes the app shell and keeps the document controls usable", async ({ page }) => {
  await page.setViewportSize({ width: 700, height: 760 });
  await openWorkspace(page);
  await page.getByRole("button", { name: "检查裁剪与分栏" }).click();
  await page.getByRole("button", { name: /确认裁剪与分栏并开始框题/ }).click();
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
  await page.getByRole("combobox", { name: "分栏数量" }).selectOption("2");
  await expect(page.locator(".batch-save-state")).toHaveText("保存失败，正在重试", { timeout: 15_000 });
  await expect(page.locator(".batch-save-state")).toHaveText("已保存", { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "检查裁剪与分栏" })).toBeEnabled();
});
