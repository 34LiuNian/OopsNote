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
  Spinner
} from "@primer/react";
import { sileo } from "sileo";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { TagPicker } from "./TagPicker";
import { TagSelectorRow } from "./TagSelectorRow";
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

export function UploadForm() {
  const [files, setFiles] = useState<File[]>([]);
  const [index, setIndex] = useState(0);
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [questionNo, setQuestionNo] = useState("");
  const [notes, setNotes] = useState("");
  const [difficultyLeft, setDifficultyLeft] = useState("");
  const [difficultyRight, setDifficultyRight] = useState("");
  const [questionType, setQuestionType] = useState("");
  const [sourceTags, setSourceTags] = useState<string[]>([]);
  const [knowledgeTags, setKnowledgeTags] = useState<string[]>([]);
  const [errorTags, setErrorTags] = useState<string[]>([]);
  const [customTags, setCustomTags] = useState<string[]>([]);
  const { effectiveDimensions: tagStyles } = useTagDimensions();
  const [isLoading, setIsLoading] = useState(false);
  const [lastTaskId, setLastTaskId] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const singleInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const difficultyRightRef = useRef<HTMLInputElement | null>(null);

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
    if (images.length > 0) {
      sileo.success({ title: `已导入 ${images.length} 张图片` });
    }
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
    sileo.info({ title: "已跳过，进入下一张" });
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

    try {
      const leftScore = difficultyLeft.trim();
      const rightScore = difficultyRight.trim();
      if ((leftScore && !rightScore) || (!leftScore && rightScore)) {
        setError("分数请填写为 a/b（两段都要填）");
        setIsLoading(false);
        return;
      }
      const difficultyValue = leftScore && rightScore ? `${leftScore}/${rightScore}` : undefined;

      const payload: Record<string, unknown> = {
        subject,
        notes,
        question_no: questionNo.trim() || undefined,
        source: sourceTags.length > 0 ? sourceTags[0] : undefined,
        question_type: questionType || undefined,
        difficulty: difficultyValue,
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
      sileo.success({
        title: "已入队",
        description: "进入下一张",
        button: {
          title: "查看任务",
          onClick: () => window.location.href = `/tasks/${id}`,
        },
      });
      moveNext();
    } catch (err) {
      sileo.error({
        title: "上传失败",
        description: err instanceof Error ? err.message : "请稍后重试",
      });
      setIsLoading(false);
    }

    setIsLoading(false);
  }, [
    convertFileToBase64,
    currentFile,
    customTags,
    difficultyLeft,
    difficultyRight,
    errorTags,
    knowledgeTags,
    moveNext,
    notes,
    questionNo,
    questionType,
    sourceTags,
    subject,
  ]);

  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'column', 'row'], gap: 4, height: '100%' }}>
      {/* Left: Annotation */}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Box>
          <Heading as="h1" sx={{ fontSize: 4, mb: 1 }}>新建题目</Heading>
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

        <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3, mt: 3 }}>
            <FormControl>
              <FormControl.Label>难度</FormControl.Label>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  border: '1px solid',
                  borderColor: 'border.default',
                  borderRadius: 2,
                  overflow: 'hidden',
                  ':focus-within': {
                    borderColor: 'accent.fg',
                    boxShadow: '0 0 0 3px color-mix(in srgb, accent.fg 20%, transparent)',
                  },
                }}
              >
                <TextInput
                  placeholder="题号"
                  value={difficultyLeft}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next.includes("/")) {
                      const [left, right] = next.split("/");
                      setDifficultyLeft(left.trim());
                      setDifficultyRight(right.trim());
                      difficultyRightRef.current?.focus();
                      return;
                    }
                    setDifficultyLeft(next);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "/") {
                      e.preventDefault();
                      difficultyRightRef.current?.focus();
                    }
                  }}
                  sx={{
                    flex: 1,
                    border: 'none',
                    borderRadius: 0,
                    input: {
                      textAlign: 'center',
                    },
                    ':focus': {
                      boxShadow: 'none',
                    },
                  }}
                />
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    px: 2,
                    color: 'fg.muted',
                    userSelect: 'none',
                  }}
                >
                  /
                </Box>
                <TextInput
                  placeholder="总题数"
                  value={difficultyRight}
                  onChange={(e) => setDifficultyRight(e.target.value)}
                  ref={difficultyRightRef}
                  sx={{
                    flex: 1,
                    border: '0px solid',
                    borderRadius: 0,
                    input: {
                      textAlign: 'center',

                      outline: 'none',
                    },
                    ':focus': {
                      boxShadow: 'none',
                    },
                  }}
                />
              </Box>
            </FormControl>
            <FormControl>
              <FormControl.Label>备注</FormControl.Label>
              <TextInput
                // placeholder="比如：易错点、你自己的想法..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                block
              />
            </FormControl>
            {/* <Box /> */}
          </Box>

          <TagSelectorRow
            sourceValue={sourceTags}
            onSourceChange={setSourceTags}
            knowledgeValue={knowledgeTags}
            onKnowledgeChange={setKnowledgeTags}
            errorValue={errorTags}
            onErrorChange={setErrorTags}
            customValue={customTags}
            onCustomChange={setCustomTags}
            styles={tagStyles}
          />

          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <Button
              size="small"
              variant="invisible"
              onClick={() => setShowAdvanced((prev) => !prev)}
            >
              {showAdvanced ? "收起高级选项" : "展开高级选项"}
            </Button>
          </Box>

          {showAdvanced && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
                <FormControl>
                  <FormControl.Label>题号</FormControl.Label>
                  <TextInput
                    // placeholder="例如：A100502.14"
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

              <FormControl>
                <FormControl.Label>题型</FormControl.Label>
                <Select value={questionType} onChange={(e) => setQuestionType(e.target.value)} block>
                  <Select.Option value="">自动识别</Select.Option>
                  <Select.Option value="选择题">选择题</Select.Option>
                  <Select.Option value="多选题">多选题</Select.Option>
                  <Select.Option value="填空题">填空题</Select.Option>
                  <Select.Option value="解答题">解答题</Select.Option>
                  <Select.Option value="其它">其它</Select.Option>
                </Select>
              </FormControl>
            </Box>
          )}

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
          borderLeftColor: ["border.muted", "border.muted", "border.muted"],
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
