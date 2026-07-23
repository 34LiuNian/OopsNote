import { mapCroppedRectToOriginalSource, type DocumentCropRect, type SelectionModel } from "@/components/batch-continuous";

export async function exportSelectionImage(
  selection: SelectionModel,
  crop: DocumentCropRect,
  getPageImage: (pageIndex: number) => Promise<File>,
): Promise<Blob> {
  const parts = [...selection.slices].sort((a, b) => a.order - b.order);
  const images = await Promise.all(parts.map(async (part) => ({
    part,
    bitmap: await createImageBitmap(await getPageImage(part.pageIndex)),
  })));
  try {
    const crops = images.map(({ part, bitmap }) => {
      const rect = mapCroppedRectToOriginalSource(part.rect, crop);
      return {
        bitmap,
        x: Math.round(rect.x * bitmap.width),
        y: Math.round(rect.y * bitmap.height),
        width: Math.max(1, Math.round(rect.width * bitmap.width)),
        height: Math.max(1, Math.round(rect.height * bitmap.height)),
      };
    });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(...crops.map((part) => part.width));
    canvas.height = crops.reduce((height, part) => height + part.height, 0);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("无法创建裁剪画布");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    let y = 0;
    for (const part of crops) {
      context.drawImage(part.bitmap, part.x, part.y, part.width, part.height, 0, y, part.width, part.height);
      y += part.height;
    }
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("无法导出选区图片")), "image/png");
    });
  } finally {
    images.forEach(({ bitmap }) => bitmap.close());
  }
}
