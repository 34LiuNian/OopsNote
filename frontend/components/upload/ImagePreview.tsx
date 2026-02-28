"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, Text } from "@primer/react";

type PanZoomState = {
  scale: number;
  x: number;
  y: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

/**
 * 图片预览组件（支持拖拽和缩放）
 */
export function ImagePreview({ file }: { file: File }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [url, setUrl] = useState<string>("");
  const [baseScale, setBaseScale] = useState(1);
  const [state, setState] = useState<PanZoomState>({ scale: 1, x: 0, y: 0 });
  const dragRef = useRef<{
    active: boolean;
    pointerId: number | null;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  }>({ active: false, pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0 });

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    setBaseScale(1);
    setState({ scale: 1, x: 0, y: 0 });
    return () => {
      try {
        URL.revokeObjectURL(nextUrl);
      } catch {
        // ignore
      }
    };
  }, [file]);

  const zoomBy = useCallback((factor: number) => {
    setState((prev) => ({ ...prev, scale: clamp(prev.scale * factor, 0.5, 4) }));
  }, []);

  const reset = useCallback(() => {
    setState({ scale: 1, x: 0, y: 0 });
  }, []);

  const recomputeBaseScale = useCallback(() => {
    const container = containerRef.current;
    const image = imageRef.current;
    if (!container || !image) return;
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const naturalWidth = image.naturalWidth || image.width;
    const naturalHeight = image.naturalHeight || image.height;
    if (!containerWidth || !containerHeight || !naturalWidth || !naturalHeight) return;
    setBaseScale(Math.min(containerWidth / naturalWidth, containerHeight / naturalHeight, 1));
  }, []);

  useEffect(() => {
    recomputeBaseScale();
    const handleResize = () => recomputeBaseScale();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [recomputeBaseScale]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (!containerRef.current) return;
    dragRef.current.active = true;
    dragRef.current.pointerId = e.pointerId;
    dragRef.current.startX = e.clientX;
    dragRef.current.startY = e.clientY;
    dragRef.current.originX = state.x;
    dragRef.current.originY = state.y;
    try {
      containerRef.current.setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }, [state.x, state.y]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current.active) return;
    if (dragRef.current.pointerId !== e.pointerId) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setState((prev) => ({ ...prev, x: dragRef.current.originX + dx, y: dragRef.current.originY + dy }));
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    if (dragRef.current.pointerId !== e.pointerId) return;
    dragRef.current.active = false;
    dragRef.current.pointerId = null;
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && Math.abs(e.deltaY) < 1) return;
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    zoomBy(factor);
  }, [zoomBy]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Text sx={{ fontSize: 1, color: 'fg.muted' }}>{file.name}</Text>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button size="small" onClick={() => zoomBy(1.2)}>放大</Button>
          <Button size="small" onClick={() => zoomBy(1 / 1.2)}>缩小</Button>
          <Button size="small" onClick={reset}>重置</Button>
        </Box>
      </Box>

      <Box
        ref={containerRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
        sx={{
          flex: 1,
          minHeight: 320,
          border: '1px solid',
          borderColor: 'border.default',
          borderRadius: 2,
          bg: 'canvas.default',
          overflow: 'hidden',
          touchAction: 'none',
          position: 'relative',
          cursor: 'grab',
          userSelect: 'none',
        }}
      >
        {url ? (
          <Box
            as="img"
            ref={imageRef}
            src={url}
            alt={file.name}
            draggable={false}
            onLoad={recomputeBaseScale}
            sx={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              maxWidth: 'none',
              maxHeight: 'none',
              transform: `translate(calc(-50% + ${state.x}px), calc(-50% + ${state.y}px)) scale(${baseScale * state.scale})`,
              transformOrigin: 'center',
              pointerEvents: 'none',
            }}
          />
        ) : null}
      </Box>
    </Box>
  );
}
