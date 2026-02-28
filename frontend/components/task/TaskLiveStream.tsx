"use client";

import { Box, Text } from "@primer/react";

interface TaskLiveStreamProps {
  streamProgress: string[];
}

export function TaskLiveStream({ streamProgress }: TaskLiveStreamProps) {
  return (
    <Box
      sx={{
        position: "fixed",
        right: 24,
        bottom: 24,
        width: 320,
        maxWidth: "calc(100vw - 32px)",
        maxHeight: 240,
        overflowY: "auto",
        p: 2,
        bg: "canvas.subtle",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "border.default",
        boxShadow: "shadow.large",
        zIndex: 30,
      }}
    >
      <Text sx={{ fontWeight: "bold", display: "block", mb: 1 }}>实时进度</Text>
      <Box sx={{ whiteSpace: "pre-wrap", fontFamily: "mono", fontSize: 1 }}>
        {streamProgress.length > 0
          ? streamProgress.map((line) => `• ${line}`).join("\n")
          : "• 等待进度更新..."}
      </Box>
    </Box>
  );
}
