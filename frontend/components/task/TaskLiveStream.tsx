"use client";

import { useState, useEffect, useRef } from "react";
import { Box, IconButton, Text } from "@primer/react";
import { XIcon, PulseIcon } from "@primer/octicons-react";

interface TaskLiveStreamProps {
  streamProgress: string[];
}

export function TaskLiveStream({ streamProgress }: TaskLiveStreamProps) {
  const [minimized, setMinimized] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [streamProgress]);

  if (minimized) {
    return (
      <Box
        onClick={() => setMinimized(false)}
        className="oops-glass"
        sx={{
          position: "fixed",
          right: 20,
          bottom: 20,
          width: 44,
          height: 44,
          borderRadius: "50%",
          border: "1px solid",
          borderColor: "border.default",
          boxShadow: "var(--oops-shadow-lg)",
          zIndex: 30,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          color: "accent.fg",
          animation: "pulse 2s ease-in-out infinite",
          "&:hover": { transform: "scale(1.1)" },
          transition: "transform var(--oops-transition-fast)",
        }}
      >
        <PulseIcon size={18} />
      </Box>
    );
  }

  return (
    <Box
      className="oops-glass"
      sx={{
        position: "fixed",
        right: 20,
        bottom: 20,
        width: 340,
        maxWidth: "calc(100vw - 32px)",
        borderRadius: "var(--oops-radius-md)",
        border: "1px solid",
        borderColor: "border.default",
        boxShadow: "var(--oops-shadow-float)",
        zIndex: 30,
        overflow: "hidden",
        animation: "slideUp 0.2s ease-out",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 3,
          py: 2,
          borderBottom: "1px solid",
          borderColor: "border.muted",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Box
            sx={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              bg: "success.fg",
              animation: "pulse 2s ease-in-out infinite",
            }}
          />
          <Text sx={{ fontWeight: 600, fontSize: 1 }}>实时进度</Text>
        </Box>
        <IconButton
          icon={XIcon}
          aria-label="最小化"
          size="small"
          variant="invisible"
          onClick={() => setMinimized(true)}
          sx={{ color: "fg.muted" }}
        />
      </Box>

      {/* Content */}
      <Box
        ref={scrollRef}
        sx={{
          maxHeight: 200,
          overflowY: "auto",
          px: 3,
          py: 2,
        }}
      >
        {streamProgress.length > 0 ? (
          streamProgress.map((line, idx) => (
            <Box
              key={idx}
              sx={{
                display: "flex",
                alignItems: "flex-start",
                gap: 2,
                py: "3px",
                fontSize: 0,
                fontFamily: "mono",
                color: idx === streamProgress.length - 1 ? "fg.default" : "fg.muted",
                animation: idx === streamProgress.length - 1 ? "fadeIn 0.3s ease-out" : "none",
              }}
            >
              <Text sx={{ color: "accent.fg", flexShrink: 0 }}>›</Text>
              <Text sx={{ wordBreak: "break-word" }}>{line}</Text>
            </Box>
          ))
        ) : (
          <Text sx={{ fontSize: 0, color: "fg.muted", fontFamily: "mono" }}>等待进度更新...</Text>
        )}
      </Box>
    </Box>
  );
}
