"use client";

import { Box, Button, Text } from "@/components/ui/primitives";
import { ImageSelectionStage, NormalizedRectEditor } from "@/components/image-selection";
import { notify } from "@/lib/notify";
import type { DiagramImageTone, NormalizedRect } from "@/types/api";
import sxStyles from "./FigureCropper.sx.module.css";

export const FULL_IMAGE_CROP: NormalizedRect = { x: 0, y: 0, width: 1, height: 1 };

export function FigureCropper({
  imageUrl,
  value,
  tone,
  onChange,
  onToneChange,
  showToneControls = true,
}: {
  imageUrl: string;
  value: NormalizedRect;
  tone: DiagramImageTone;
  onChange: (value: NormalizedRect) => void;
  onToneChange: (tone: DiagramImageTone) => void;
  showToneControls?: boolean;
}) {
  return (
    <Box className="figure-cropper">
      <Box className="figure-cropper__toolbar">
        <Text className={sxStyles.sx1}>裁剪范围</Text>
        <Button size="small" variant="invisible" onClick={() => onChange(FULL_IMAGE_CROP)}>重置选区</Button>
      </Box>
      <Box className="figure-cropper__viewport">
        <ImageSelectionStage
          src={imageUrl}
          alt="附图裁剪原图"
          tone={tone}
        >
          <NormalizedRectEditor
            value={value}
            interaction="redraw"
            onChange={onChange}
            onTooSmall={() => notify.info({ title: "选区太小", description: "请拖出一个更大的附图区域。" })}
          />
        </ImageSelectionStage>
      </Box>
      {showToneControls ? (
        <Box className="figure-cropper__tone">
          <Text className={sxStyles.sx2}>显示</Text>
          <Button aria-pressed={tone === "auto"} size="small" variant={tone === "auto" ? "primary" : "default"} onClick={() => onToneChange("auto")}>自动适配</Button>
          <Button aria-pressed={tone === "original"} size="small" variant={tone === "original" ? "primary" : "default"} onClick={() => onToneChange("original")}>原图</Button>
        </Box>
      ) : null}
    </Box>
  );
}
