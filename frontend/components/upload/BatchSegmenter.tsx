"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Box } from "@/components/ui/primitives";

type CropRect = { x: number; y: number; width: number; height: number };

export type SegmentRect = { x: number; y: number; width: number; height: number };

export type SegmentedImage = {
  id: string;
  blob?: Blob;
  filename: string;
  mimeType: string;
  rect: SegmentRect;
  questionNo?: number;
  status?: "pending" | "processing" | "completed" | "failed";
  taskId?: string;
  problemIds?: string[];
  error?: string;
};

type BatchSegmenterProps = {
  file: File;
  initialSegments?: SegmentedImage[];
  onSegmentsChange: (segments: SegmentedImage[]) => void;
  inverted?: boolean;
  nextQuestionNo: number;
  onOpenTask: (taskId: string) => void;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("无法导出裁剪图片")), "image/png");
  });
}

export function BatchSegmenter({ file, initialSegments = [], onSegmentsChange, inverted = false, nextQuestionNo, onOpenTask }: BatchSegmenterProps) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; dragging: boolean }>({ startX: 0, startY: 0, dragging: false });
  const initialSegmentsRef = useRef(initialSegments);
  const onSegmentsChangeRef = useRef(onSegmentsChange);
  const [url, setUrl] = useState("");
  const [draft, setDraft] = useState<CropRect | null>(null);
  const [segments, setSegments] = useState<SegmentedImage[]>(initialSegments);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    initialSegmentsRef.current = initialSegments;
  }, [initialSegments]);

  useEffect(() => {
    onSegmentsChangeRef.current = onSegmentsChange;
  }, [onSegmentsChange]);

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    setDraft(null);
    setSegments(initialSegmentsRef.current);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  useEffect(() => {
    onSegmentsChangeRef.current(segments);
  }, [segments]);

  const pointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const image = imageRef.current;
    if (!image) return;
    const bounds = image.getBoundingClientRect();
    dragRef.current = {
      startX: clamp(event.clientX - bounds.left, 0, bounds.width),
      startY: clamp(event.clientY - bounds.top, 0, bounds.height),
      dragging: true,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDraft({ x: dragRef.current.startX, y: dragRef.current.startY, width: 0, height: 0 });
  }, []);

  const pointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const image = imageRef.current;
    if (!image || !dragRef.current.dragging) return;
    const bounds = image.getBoundingClientRect();
    const currentX = clamp(event.clientX - bounds.left, 0, bounds.width);
    const currentY = clamp(event.clientY - bounds.top, 0, bounds.height);
    setDraft({
      x: Math.min(dragRef.current.startX, currentX),
      y: Math.min(dragRef.current.startY, currentY),
      width: Math.abs(currentX - dragRef.current.startX),
      height: Math.abs(currentY - dragRef.current.startY),
    });
  }, []);

  const addSegment = useCallback(async (crop: CropRect) => {
    const image = imageRef.current;
    if (!image || crop.width < 12 || crop.height < 12 || isExporting) return;
    setIsExporting(true);
    try {
      const scaleX = image.naturalWidth / image.clientWidth;
      const scaleY = image.naturalHeight / image.clientHeight;
      const sx = Math.round(crop.x * scaleX);
      const sy = Math.round(crop.y * scaleY);
      const sw = Math.round(crop.width * scaleX);
      const sh = Math.round(crop.height * scaleY);
      const rect = {
        x: crop.x / image.clientWidth,
        y: crop.y / image.clientHeight,
        width: crop.width / image.clientWidth,
        height: crop.height / image.clientHeight,
      };
      const source = await createImageBitmap(file);
      try {
        const canvas = document.createElement("canvas");
        canvas.width = sw;
        canvas.height = sh;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("无法创建画布");
        context.drawImage(source, sx, sy, sw, sh, 0, 0, sw, sh);
        const blob = await canvasToBlob(canvas);
        setSegments((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            blob,
            filename: `${file.name.replace(/\.[^.]+$/, "")}-${current.length + 1}.png`,
            mimeType: "image/png",
            rect,
            questionNo: nextQuestionNo,
            status: "pending",
          },
        ]);
        setDraft(null);
      } finally {
        source.close();
      }
    } finally {
      setIsExporting(false);
    }
  }, [file, isExporting, nextQuestionNo]);

  const pointerUp = useCallback(() => {
    dragRef.current.dragging = false;
    if (draft) void addSegment(draft);
  }, [addSegment, draft]);

  const pointerCancel = useCallback(() => {
    dragRef.current.dragging = false;
    setDraft(null);
  }, []);

  const removeSegment = useCallback((id: string) => {
    setSegments((current) => current.filter((segment) => segment.id !== id));
  }, []);

  return (
    <Box className={`batch-segmenter${inverted ? " is-inverted" : ""}`}>
      <Box
        className="batch-segmenter__canvas"
      >
        <Box
          className="batch-segmenter__image"
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerCancel={pointerCancel}
        >
          {url && <img ref={imageRef} src={url} alt={file.name} draggable={false} />}
          {segments.map((segment, index) => segment.rect && (
            <button
              type="button"
              key={segment.id}
              className={`batch-segmenter__selection is-${segment.status ?? "pending"}`}
              title={segment.error || (segment.taskId ? "在新标签页打开任务" : `移除题目 ${segment.questionNo ?? index + 1} / 本页 ${index + 1}`)}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => segment.taskId ? onOpenTask(segment.taskId) : removeSegment(segment.id)}
              style={{
                left: `${segment.rect.x * 100}%`,
                top: `${segment.rect.y * 100}%`,
                width: `${segment.rect.width * 100}%`,
                height: `${segment.rect.height * 100}%`,
              }}
            >
              <span>{segment.questionNo ?? index + 1} / {index + 1}</span>
            </button>
          ))}
          {draft && <Box className="batch-segmenter__draft" style={{ left: draft.x, top: draft.y, width: draft.width, height: draft.height }} />}
        </Box>
      </Box>
    </Box>
  );
}
