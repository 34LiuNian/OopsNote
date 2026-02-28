"use client";

import { Box, Spinner, Text } from "@primer/react";

/**
 * 统一的加载动画组件
 * 用于替代分散的 Spinner、Label、Text 等加载状态
 * 
 * @example
 * ```tsx
 * <LoadingSpinner size="large" text="加载中..." />
 * ```
 */
export function LoadingSpinner({
  size = "medium",
  text,
  fullScreen = false,
}: {
  size?: "small" | "medium" | "large";
  text?: string;
  fullScreen?: boolean;
}) {
  const spinnerSize = size === "small" ? "small" : size === "large" ? "large" : "medium";
  
  const content = (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 3,
      }}
    >
      <Spinner size={spinnerSize} />
      {text && (
        <Text
          sx={{
            fontSize: size === "large" ? 3 : 2,
            color: "fg.muted",
            textAlign: "center",
          }}
        >
          {text}
        </Text>
      )}
    </Box>
  );

  if (fullScreen) {
    return (
      <Box
        sx={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bg: "canvas.subtle",
          zIndex: 9999,
        }}
      >
        {content}
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flex: 1,
        minHeight: 200,
        p: 5,
      }}
    >
      {content}
    </Box>
  );
}

/**
 * 骨架屏加载组件
 * 用于列表、卡片等内容的加载状态
 * 
 * @example
 * ```tsx
 * <LoadingSkeleton count={5} />
 * ```
 */
export function LoadingSkeleton({
  count = 3,
  height = 60,
  gap = 2,
}: {
  count?: number;
  height?: number;
  gap?: number;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: count }).map((_, index) => (
        <Box
          key={index}
          sx={{
            height,
            borderRadius: 2,
            bg: "canvas.subtle",
            animation: "pulse 1.5s ease-in-out infinite",
            "@keyframes pulse": {
              "0%": { opacity: 0.6 },
              "50%": { opacity: 1 },
              "100%": { opacity: 0.6 },
            },
          }}
        />
      ))}
    </Box>
  );
}

/**
 * 列表骨架屏（专门用于列表项）
 */
export function ListSkeleton({
  count = 5,
  showAvatar = false,
}: {
  count?: number;
  showAvatar?: boolean;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {Array.from({ length: count }).map((_, index) => (
        <Box
          key={index}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 3,
            p: 3,
            borderRadius: 2,
            bg: "canvas.subtle",
            animation: "pulse 1.5s ease-in-out infinite",
            "@keyframes pulse": {
              "0%": { opacity: 0.6 },
              "50%": { opacity: 1 },
              "100%": { opacity: 0.6 },
            },
          }}
        >
          {showAvatar && (
            <Box
              sx={{
                width: 40,
                height: 40,
                borderRadius: "50%",
                bg: "canvas.default",
              }}
            />
          )}
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
            <Box
              sx={{
                height: 16,
                width: "60%",
                borderRadius: 2,
                bg: "canvas.default",
              }}
            />
            <Box
              sx={{
                height: 12,
                width: "40%",
                borderRadius: 2,
                bg: "canvas.default",
              }}
            />
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/**
 * 卡片骨架屏（专门用于卡片布局）
 */
export function CardSkeleton({
  count = 4,
  columns = 2,
}: {
  count?: number;
  columns?: number;
}) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          _: "1fr",
          narrow: (columns > 1 ? `repeat(${columns}, 1fr)` : "1fr") as any,
          wide: (columns > 2 ? `repeat(${columns}, 1fr)` : "1fr") as any,
        } as any,
        gap: 3,
      }}
    >
      {Array.from({ length: count }).map((_, index) => (
        <Box
          key={index}
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: 2,
            p: 3,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "border.default",
            bg: "canvas.subtle",
            animation: "pulse 1.5s ease-in-out infinite",
            "@keyframes pulse": {
              "0%": { opacity: 0.6 },
              "50%": { opacity: 1 },
              "100%": { opacity: 0.6 },
            },
          }}
        >
          <Box
            sx={{
              height: 120,
              borderRadius: 2,
              bg: "canvas.default",
            }}
          />
          <Box
            sx={{
              height: 16,
              width: "80%",
              borderRadius: 2,
              bg: "canvas.default",
            }}
          />
          <Box
            sx={{
              height: 12,
              width: "60%",
              borderRadius: 2,
              bg: "canvas.default",
            }}
          />
        </Box>
      ))}
    </Box>
  );
}
