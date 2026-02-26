"use client";

import { Box } from "@primer/react";
import { API_BASE } from "../lib/api";

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

  if (!asset?.path) {
    return (
      <Box
        sx={{
          width: `${width}px`,
          height: `${height}px`,
          backgroundColor: "canvas.subtle",
          borderRadius: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "fg.muted",
          fontSize: 0,
        }}
      >
        无图像
      </Box>
    );
  }

  // asset.path is a relative URL like "/assets/xxx.jpg"
  // Prepend API_BASE to route through Next.js proxy
  const imageUrl = `${API_BASE}${asset.path}`;

  return (
    <Box
      sx={{
        width: `${width}px`,
        height: `${height}px`,
        borderRadius: 2,
        overflow: "hidden",
        backgroundColor: "canvas.subtle",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <img
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
      />
    </Box>
  );
}
