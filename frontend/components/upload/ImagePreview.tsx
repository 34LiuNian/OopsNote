"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Box, Button, Spinner, Text } from "@primer/react";

type CropRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

async function loadImageFromUrl(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败"));
    image.src = url;
  });
}

async function canvasToBlob(canvas: HTMLCanvasElement, mimeType: string = "image/png", quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("图像导出失败"));
          return;
        }
        resolve(blob);
      },
      mimeType,
      quality,
    );
  });
}

export type ImagePreviewExport = {
  blob: Blob;
  filename: string;
  mimeType: string;
};

export type ImagePreviewHandle = {
  exportImage: () => Promise<ImagePreviewExport | null>;
};

export const ImagePreview = forwardRef<ImagePreviewHandle, { file: File }>(function ImagePreview({ file }, ref) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const latestFileRef = useRef<File>(file);
  const [url, setUrl] = useState<string>("");
  const [editedBlob, setEditedBlob] = useState<Blob | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isCropMode, setIsCropMode] = useState(false);
  const [cropRect, setCropRect] = useState<CropRect | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; dragging: boolean }>({
    startX: 0,
    startY: 0,
    dragging: false,
  });

  useEffect(() => {
    latestFileRef.current = file;
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    setEditedBlob(null);
    setCropRect(null);
    setIsCropMode(false);
    return () => {
      try {
        URL.revokeObjectURL(nextUrl);
      } catch {
        // ignore
      }
    };
  }, [file]);

  const commitBlob = useCallback((blob: Blob) => {
    setEditedBlob(blob);
    setCropRect(null);
    setIsCropMode(false);
    setUrl((prev) => {
      try {
        if (prev) URL.revokeObjectURL(prev);
      } catch {
        // ignore
      }
      return URL.createObjectURL(blob);
    });
  }, []);

  const rotate = useCallback(async (clockwise: boolean) => {
    if (!url) return;
    setIsProcessing(true);
    try {
      const image = await loadImageFromUrl(url);
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalHeight;
      canvas.height = image.naturalWidth;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("无法创建画布");

      context.translate(canvas.width / 2, canvas.height / 2);
      context.rotate((clockwise ? 90 : -90) * Math.PI / 180);
      context.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);

      const blob = await canvasToBlob(canvas, "image/png");
      commitBlob(blob);
    } finally {
      setIsProcessing(false);
    }
  }, [commitBlob, url]);

  const applyCrop = useCallback(async () => {
    if (!url || !cropRect || !imageRef.current) return;
    const imageElement = imageRef.current;
    const displayWidth = imageElement.clientWidth;
    const displayHeight = imageElement.clientHeight;
    if (!displayWidth || !displayHeight) return;

    const sx = Math.floor((cropRect.x / displayWidth) * imageElement.naturalWidth);
    const sy = Math.floor((cropRect.y / displayHeight) * imageElement.naturalHeight);
    const sw = Math.floor((cropRect.width / displayWidth) * imageElement.naturalWidth);
    const sh = Math.floor((cropRect.height / displayHeight) * imageElement.naturalHeight);
    if (sw < 8 || sh < 8) return;

    setIsProcessing(true);
    try {
      const image = await loadImageFromUrl(url);
      const canvas = document.createElement("canvas");
      canvas.width = sw;
      canvas.height = sh;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("无法创建画布");

      context.drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);
      const blob = await canvasToBlob(canvas, "image/png");
      commitBlob(blob);
    } finally {
      setIsProcessing(false);
    }
  }, [commitBlob, cropRect, url]);

  const reset = useCallback(() => {
    const nextUrl = URL.createObjectURL(latestFileRef.current);
    setEditedBlob(null);
    setCropRect(null);
    setIsCropMode(false);
    setUrl((prev) => {
      try {
        if (prev) URL.revokeObjectURL(prev);
      } catch {
        // ignore
      }
      return nextUrl;
    });
  }, []);

  useImperativeHandle(ref, () => ({
    exportImage: async () => {
      if (!editedBlob) return null;
      return {
        blob: editedBlob,
        filename: latestFileRef.current.name,
        mimeType: editedBlob.type || "image/png",
      };
    },
  }), [editedBlob]);

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isCropMode || !imageRef.current) return;
    const rect = imageRef.current.getBoundingClientRect();
    const x = clamp(event.clientX - rect.left, 0, rect.width);
    const y = clamp(event.clientY - rect.top, 0, rect.height);
    dragRef.current.dragging = true;
    dragRef.current.startX = x;
    dragRef.current.startY = y;
    setCropRect({ x, y, width: 0, height: 0 });
  }, [isCropMode]);

  const onPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isCropMode || !dragRef.current.dragging || !imageRef.current) return;
    const rect = imageRef.current.getBoundingClientRect();
    const currentX = clamp(event.clientX - rect.left, 0, rect.width);
    const currentY = clamp(event.clientY - rect.top, 0, rect.height);
    const x = Math.min(dragRef.current.startX, currentX);
    const y = Math.min(dragRef.current.startY, currentY);
    const width = Math.abs(currentX - dragRef.current.startX);
    const height = Math.abs(currentY - dragRef.current.startY);
    setCropRect({ x, y, width, height });
  }, [isCropMode]);

  const onPointerUp = useCallback(() => {
    dragRef.current.dragging = false;
  }, []);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", gap: 2, alignItems: "center", justifyContent: "space-between", mb: 2, flexWrap: "wrap" }}>
        <Text sx={{ fontSize: 1, color: "fg.muted" }}>{file.name}</Text>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <Button size="small" onClick={() => void rotate(false)} disabled={isProcessing}>左转</Button>
          <Button size="small" onClick={() => void rotate(true)} disabled={isProcessing}>右转</Button>
          <Button
            size="small"
            variant={isCropMode ? "primary" : "default"}
            onClick={() => setIsCropMode((prev) => !prev)}
            disabled={isProcessing}
          >
            {isCropMode ? "取消框选" : "裁剪框选"}
          </Button>
          <Button size="small" onClick={() => void applyCrop()} disabled={isProcessing || !cropRect || cropRect.width < 8 || cropRect.height < 8}>应用裁剪</Button>
          <Button size="small" onClick={reset} disabled={isProcessing}>重置</Button>
        </Box>
      </Box>

      <Box
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        sx={{
          flex: 1,
          minHeight: 320,
          border: "1px solid",
          borderColor: "border.default",
          borderRadius: 2,
          bg: "canvas.default",
          overflow: "hidden",
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          userSelect: "none",
          cursor: isCropMode ? "crosshair" : "default",
        }}
      >
        {url ? (
          <Box
            as="img"
            ref={imageRef}
            src={url}
            alt={file.name}
            draggable={false}
            sx={{
              maxWidth: "100%",
              maxHeight: "100%",
              width: "auto",
              height: "auto",
            }}
          />
        ) : null}
        {cropRect ? (
          <Box
            sx={{
              position: "absolute",
              left: cropRect.x,
              top: cropRect.y,
              width: cropRect.width,
              height: cropRect.height,
              border: "2px solid",
              borderColor: "accent.fg",
              bg: "accent.subtle",
              pointerEvents: "none",
            }}
          />
        ) : null}
        {isProcessing ? (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              bg: "canvas.overlay",
            }}
          >
            <Spinner size="large" />
          </Box>
        ) : null}
      </Box>
    </Box>
  );
});
