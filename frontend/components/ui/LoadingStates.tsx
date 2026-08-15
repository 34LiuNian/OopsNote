"use client";

import { Box, Spinner, Text } from "@/components/ui/primitives";
import styles from "./LoadingStates.module.css";

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
    <Box className={styles.content}>
      <Spinner size={spinnerSize} />
      {text && (
        <Text className={size === "large" ? styles.textLarge : styles.text}>
          {text}
        </Text>
      )}
    </Box>
  );

  if (fullScreen) {
    return (
      <Box className={styles.fullScreen}>
        {content}
      </Box>
    );
  }

  return (
    <Box className={styles.loadingState}>
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
    <Box className={styles.column} style={{ "--oops-geometry-gap": `${gap * 4}px` } as React.CSSProperties}>
      {Array.from({ length: count }).map((_, index) => (
        <Box key={index} className={styles.skeleton} style={{ "--oops-geometry-height": `${height}px` } as React.CSSProperties} />
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
    <Box className={styles.column}>
      {Array.from({ length: count }).map((_, index) => (
        <Box
          key={index}
          className={styles.listRow}
        >
          {showAvatar && (
            <Box
              className={styles.avatarSkeleton}
            />
          )}
          <Box className={styles.listContent}>
            <Box
              className={styles.lineWide}
            />
            <Box
              className={styles.lineNarrow}
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
    <Box className={styles.cardGrid} data-columns={columns}>
      {Array.from({ length: count }).map((_, index) => (
        <Box
          key={index}
          className={styles.card}
        >
          <Box
            className={styles.cardImage}
          />
          <Box
            className={styles.cardLineWide}
          />
          <Box
            className={styles.cardLineNarrow}
          />
        </Box>
      ))}
    </Box>
  );
}
