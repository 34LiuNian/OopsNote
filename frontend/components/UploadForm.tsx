"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { 
  Box, 
  Button, 
  FormControl, 
  Heading, 
  TextInput, 
  Select, 
  Text, 
  Label,
  Flash,
  Spinner
} from "@primer/react";
import Link from "next/link";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { TagPicker } from "./TagPicker";
import { useTagDimensions } from "../features/tags";

const DEFAULT_SUBJECT = "math";

type PanZoomState = {
  scale: number;
  x: number;
  y: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function ImagePanZoom({ file }: { file: File }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [url, setUrl] = useState<string>("");
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
    // Trackpad/mouse wheel zoom.
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
        <Box
          as="img"
          src={url}
          alt={file.name}
          draggable={false}
          sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            maxWidth: 'none',
            maxHeight: 'none',
            transform: `translate(calc(-50% + ${state.x}px), calc(-50% + ${state.y}px)) scale(${state.scale})`,
            transformOrigin: 'center',
            pointerEvents: 'none',
          }}
        />
      </Box>
    </Box>
  );
}

export function UploadForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [index, setIndex] = useState(0);
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [questionNo, setQuestionNo] = useState("");
  const [notes, setNotes] = useState("");
  const [source, setSource] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [knowledgeTags, setKnowledgeTags] = useState<string[]>([]);
  const [errorTags, setErrorTags] = useState<string[]>([]);
  const [customTags, setCustomTags] = useState<string[]>([]);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastTaskId, setLastTaskId] = useState<string>("");
  const [error, setError] = useState<string>("");

  const singleInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    // Enable folder import on Chromium browsers.
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
    // Prefer camera on mobile when available.
    if (singleInputRef.current) {
      singleInputRef.current.setAttribute('capture', 'environment');
    }
  }, []);

  const currentFile = files[index] ?? null;
  const remaining = Math.max(0, files.length - index);

  const setPickedFiles = useCallback((picked: File[]) => {
    const images = picked.filter((f) => (f.type || '').startsWith('image/'));
    setFiles(images);
    setIndex(0);
    setLastTaskId("");
    setStatusMessage(images.length > 0 ? `已导入 ${images.length} 张图片` : "未选择图片");
    setError("");
  }, []);

  const onSinglePicked = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const list = Array.from(event.target.files ?? []);
    // reset value so selecting same file again triggers change
    event.target.value = "";
    setPickedFiles(list);
  }, [setPickedFiles]);

  const onFolderPicked = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const list = Array.from(event.target.files ?? []);
    event.target.value = "";
    setPickedFiles(list);
  }, [setPickedFiles]);

  const convertFileToBase64 = useCallback(async (input: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        if (typeof result === "string") {
          const data = result.split(",").pop() ?? "";
          resolve(data || "");
        } else {
          reject(new Error("无法读取文件"));
        }
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(input);
    });
  }, []);

  const moveNext = useCallback(() => {
    setIndex((prev) => {
      const next = prev + 1;
      return next;
    });
  }, []);

  const handleSkip = useCallback(() => {
    if (!currentFile) return;
    setStatusMessage("已跳过，进入下一张");
    setError("");
    moveNext();
  }, [currentFile, moveNext]);

  const handleSubmitAndQueue = useCallback(async () => {
    if (!currentFile) {
      setError("请先导入图片");
      return;
    }
    setIsLoading(true);
    setError("");
    setStatusMessage("正在入队...");

    try {
      const payload: Record<string, unknown> = {
        subject,
        notes,
        question_no: questionNo.trim() || undefined,
        source: source.trim() || undefined,
        difficulty: difficulty.trim() || undefined,
        knowledge_tags: knowledgeTags,
        error_tags: errorTags,
        user_tags: customTags,
      };

      payload.image_base64 = await convertFileToBase64(currentFile);
      payload.filename = currentFile.name;
      payload.mime_type = currentFile.type || "image/png";

      const data = await fetchJson<TaskResponse>("/upload?auto_process=false", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      const id = data.task.id;
      // Kick off background processing.
      await fetchJson<TaskResponse>(`/tasks/${id}/process?background=true`, {
        method: "POST",
      });

      setLastTaskId(id);
      setStatusMessage("已入队，进入下一张");
      moveNext();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
      setIsLoading(false);
    }

    setIsLoading(false);
  }, [convertFileToBase64, currentFile, difficulty, errorTags, knowledgeTags, moveNext, notes, questionNo, source, subject, customTags]);

  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'column', 'row'], gap: 4, height: '100%' }}>
      {/* Left: Annotation */}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Box>
          <Heading as="h1" sx={{ fontSize: 4, mb: 1 }}>快速打标</Heading>
          <Text as="p" sx={{ color: 'fg.muted', fontSize: 1 }}>
            拍照/导入后，先人工打标，再提交入队处理。
          </Text>
        </Box>

        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            ref={singleInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={onSinglePicked}
            style={{ display: 'none' }}
          />
          <input
            ref={folderInputRef}
            type="file"
            multiple
            onChange={onFolderPicked}
            style={{ display: 'none' }}
          />
          <Button
            variant="primary"
            onClick={() => singleInputRef.current?.click()}
            disabled={isLoading}
          >
            拍照/选择图片
          </Button>
          <Button
            onClick={() => folderInputRef.current?.click()}
            disabled={isLoading}
          >
            导入文件夹
          </Button>
          {files.length > 0 && (
            <Label variant="secondary">剩余 {remaining} / {files.length}</Label>
          )}
        </Box>

        {statusMessage && (
          <Flash variant="success" sx={{ display: 'flex', alignItems: 'center' }}>
            {statusMessage}{lastTaskId ? (
              <Text as="span" sx={{ ml: 2 }}>
                <Link href={`/tasks/${lastTaskId}`}>打开任务</Link>
              </Text>
            ) : null}
          </Flash>
        )}
        {error && (
          <Flash variant="danger" sx={{ display: 'flex', alignItems: 'center' }}>
            {error}
          </Flash>
        )}

        <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
            <FormControl>
              <FormControl.Label>题号（可选）</FormControl.Label>
              <TextInput
                placeholder="例如：A100502.14"
                value={questionNo}
                onChange={(e) => setQuestionNo(e.target.value)}
                block
              />
            </FormControl>
            <FormControl>
              <FormControl.Label>学科</FormControl.Label>
              <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
                <Select.Option value="math">数学</Select.Option>
                <Select.Option value="physics">物理</Select.Option>
                <Select.Option value="chemistry">化学</Select.Option>
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
            <FormControl>
              <FormControl.Label>来源（可选，批量）</FormControl.Label>
              <TextInput
                placeholder="例如：2025-一模"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                block
              />
            </FormControl>
            <FormControl>
              <FormControl.Label>难度（可选）</FormControl.Label>
              <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} block>
                <Select.Option value="">（不填）</Select.Option>
                <Select.Option value="易">易</Select.Option>
                <Select.Option value="中">中</Select.Option>
                <Select.Option value="难">难</Select.Option>
              </Select>
            </FormControl>
          </Box>

          <FormControl>
            <FormControl.Label>备注（可选）</FormControl.Label>
            <TextInput
              placeholder="比如：易错点、你自己的想法..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              block
            />
          </FormControl>

          <TagPicker
            title="知识体系（可多选，支持模糊搜索）"
            dimension="knowledge"
            value={knowledgeTags}
            onChange={setKnowledgeTags}
            placeholder="输入几个字搜索，例如：函数/单调"
            styles={tagStyles}
          />

          <TagPicker
            title="错题归因（可多选，支持模糊搜索）"
            dimension="error"
            value={errorTags}
            onChange={setErrorTags}
            placeholder="输入几个字搜索，例如：计算/概念/思路"
            styles={tagStyles}
          />

          <TagPicker
            title="自定义标签（自由输入）"
            dimension="custom"
            value={customTags}
            onChange={setCustomTags}
            placeholder="输入后回车添加"
            styles={tagStyles}
            enableRemoteSearch={false}
          />

          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <Button
              variant="primary"
              onClick={handleSubmitAndQueue}
              disabled={isLoading || !currentFile}
            >
              {isLoading ? <><Spinner size="small" sx={{ mr: 1 }} />入队中...</> : "提交并入队"}
            </Button>
            <Button onClick={handleSkip} disabled={isLoading || !currentFile}>
              跳过
            </Button>
          </Box>
        </Box>
      </Box>

      {/* Right: Image */}
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          borderLeft: ["none", "none", "1px solid"],
          borderColor: "border.default",
          pl: [0, 0, 4],
          pt: [4, 4, 0],
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Heading as="h2" sx={{ fontSize: 3 }}>图片</Heading>
          {files.length > 0 && (
            <Label variant="secondary">第 {Math.min(index + 1, files.length)} / {files.length}</Label>
          )}
        </Box>

        {!currentFile ? (
          <Box
            sx={{
              flex: 1,
              p: 5,
              textAlign: 'center',
              color: 'fg.muted',
              border: '1px dashed',
              borderColor: 'border.default',
              borderRadius: 2,
            }}
          >
            <Text as="p" sx={{ fontWeight: 'bold' }}>等待导入图片</Text>
            <Text as="p" sx={{ fontSize: 1 }}>从左侧选择拍照/多图/文件夹导入。</Text>
          </Box>
        ) : (
          <ImagePanZoom file={currentFile} />
        )}
      </Box>
    </Box>
  );
}
