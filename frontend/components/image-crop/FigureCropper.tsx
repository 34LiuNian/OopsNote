"use client";

import { Box, Button, Text } from "@/components/ui/primitives";
import { NativeImage } from "@/components/ui/NativeImage";
import { notify } from "@/lib/notify";
import type { DiagramImageTone, NormalizedRect } from "@/types/api";
import { NormalizedCropOverlay } from "./NormalizedCropOverlay";

export const FULL_IMAGE_CROP: NormalizedRect = { x: 0, y: 0, width: 1, height: 1 };

export function FigureCropper({
  imageUrl,
  value,
  tone,
  onChange,
  onToneChange,
}: {
  imageUrl: string;
  value: NormalizedRect;
  tone: DiagramImageTone;
  onChange: (value: NormalizedRect) => void;
  onToneChange: (tone: DiagramImageTone) => void;
}) {
  return (
    <Box className="figure-cropper">
      <Box className="figure-cropper__toolbar">
        <Text sx={{ fontWeight: 600, fontSize: 1 }}>裁剪范围</Text>
        <Button size="small" variant="invisible" onClick={() => onChange(FULL_IMAGE_CROP)}>重置选区</Button>
      </Box>
      <Box className={`figure-cropper__viewport${tone === "auto" ? " is-auto-tone" : ""}`}>
        <Box className="figure-cropper__canvas">
          <NativeImage src={imageUrl} alt="附图裁剪原图" draggable={false} />
          <NormalizedCropOverlay
            value={value}
            redrawInside
            onChange={onChange}
            onTooSmall={() => notify.info({ title: "选区太小", description: "请拖出一个更大的附图区域。" })}
          />
        </Box>
      </Box>
      <Box className="figure-cropper__tone">
        <Text sx={{ color: "fg.muted", fontSize: 1 }}>显示</Text>
        <Button aria-pressed={tone === "auto"} size="small" variant={tone === "auto" ? "primary" : "default"} onClick={() => onToneChange("auto")}>自动适配</Button>
        <Button aria-pressed={tone === "original"} size="small" variant={tone === "original" ? "primary" : "default"} onClick={() => onToneChange("original")}>原图</Button>
      </Box>
    </Box>
  );
}
