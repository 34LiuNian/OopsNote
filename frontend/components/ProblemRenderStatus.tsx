"use client";

import { Box, Button, Spinner, Text } from "@/components/ui/primitives";

type ProblemRenderStatusProps = {
  detected: boolean;
  status?: string | null;
  error?: string | null;
  needsReview?: boolean;
  retrying?: boolean;
  onRetry?: () => void;
};

export function ProblemRenderStatus({
  detected,
  status,
  error,
  needsReview = false,
  retrying = false,
  onRetry,
}: ProblemRenderStatusProps) {
  if (!detected || (status !== "failed" && !needsReview)) return null;

  return (
    <Box className="problem-render-status">
      <Text className="problem-render-status__title">图形重建失败，建议人工介入。</Text>
      {error ? <Text className="problem-render-status__error">{error}</Text> : null}
      {onRetry ? (
        <Button size="small" variant="default" onClick={onRetry} disabled={retrying} leadingVisual={retrying ? Spinner : undefined}>
          {retrying ? "重试渲染中..." : "重试图形渲染"}
        </Button>
      ) : null}
    </Box>
  );
}
