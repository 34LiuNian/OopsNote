"use client";

import Image from "next/image";
import { Box } from "@/components/ui/primitives";
import { useAuthenticatedAssetUrl } from "@/hooks/useAuthenticatedAssetUrl";

interface TaskThumbnailProps {
  asset?: {
    asset_id: string;
    path: string;
    mime_type?: string | null;
  } | null;
  size?: "small" | "medium" | "large";
}

const SIZE_MAP = {
  small: { width: 48, height: 48 },
  medium: { width: 64, height: 64 },
  large: { width: 80, height: 80 },
};

export function TaskThumbnail({ asset, size = "medium" }: TaskThumbnailProps) {
  const { width, height } = SIZE_MAP[size];
  const imageUrl = useAuthenticatedAssetUrl(asset?.path);

  if (!asset?.path) {
    return (
      <Box
        className="task-thumbnail task-thumbnail-empty"
        style={{
          "--oops-geometry-width": `${width}px`,
          "--oops-geometry-height": `${height}px`,
        } as React.CSSProperties}
      >
        无图像
      </Box>
    );
  }

  // Protected files are loaded as authenticated blob URLs by the shared hook.
  return (
    <Box
      className="task-thumbnail"
      style={{
        "--oops-geometry-width": `${width}px`,
        "--oops-geometry-height": `${height}px`,
      } as React.CSSProperties}
    >
      {imageUrl ? <Image
        width={width}
        height={height}
        unoptimized
        src={imageUrl}
        alt="任务缩略图"
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
        onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
          const target = e.target as HTMLImageElement;
          target.style.display = "none";
          const parent = target.parentElement;
          if (parent) {
            parent.style.color = "fg.muted";
            parent.style.fontSize = "10px";
            parent.style.textAlign = "center";
            parent.style.padding = "4px";
            parent.textContent = "加载失败";
          }
        }}
      /> : null}
    </Box>
  );
}
