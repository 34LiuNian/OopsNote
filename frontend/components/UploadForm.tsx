"use client";

import { useCallback, useState, useRef, useEffect } from "react";
import { Box, Heading, Label, Text } from "@primer/react";
import { Button, FormControl, Select, Spinner, TextInput } from "@primer/react";
import { sileo } from "sileo";
import { fetchJson } from "../lib/api";
import type { TaskResponse } from "../types/api";
import { useTagDimensions } from "../features/tags";
import { useApiError } from "../hooks/useApiError";
import { ImagePreview } from "./upload/ImagePreview";
import { AnnotationForm } from "./upload/AnnotationForm";
import { UploadQueue } from "./upload/UploadQueue";
import { TagSelectorRow } from "./TagSelectorRow";

const DEFAULT_SUBJECT = "auto"; // 默认自动识别

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
  const [showAdvanced, setShowAdvanced] = useState(false);
  const { error, handleError, clearError } = useApiError({
    defaultFallback: "上传失败，请稍后重试",
  });

  const singleInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const difficultyLeftRef = useRef<HTMLInputElement>(null);
  const difficultyRightRef = useRef<HTMLInputElement>(null);

  const currentFile = files[index] ?? null;
  const remaining = files.length - index;

  // 当切换到新图片时，自动聚焦到难度输入框
  useEffect(() => {
    console.log('[UploadForm] index 变化:', { index, filesLength: files.length, hasRef: !!difficultyLeftRef.current });
    if (files.length > 0 && index < files.length) {
      // 等待 DOM 更新后聚焦
      const timer = setTimeout(() => {
        console.log('[UploadForm] 尝试聚焦难度输入框，ref 存在:', !!difficultyLeftRef.current);
        difficultyLeftRef.current?.focus();
        console.log('[UploadForm] 聚焦完成，当前 activeElement:', document.activeElement?.tagName);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [index, files.length]);

  const setPickedFiles = useCallback((picked: File[]) => {
    const images = picked.filter((f) => (f.type || '').startsWith('image/'));
    setFiles(images);
    setIndex(0);
    setLastTaskId("");
    if (images.length > 0) {
      sileo.success({ title: `已导入 ${images.length} 张图片` });
    }
    clearError();
  }, [clearError]);

  const onSinglePicked = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files;
    if (!picked || picked.length === 0) return;
    setPickedFiles(Array.from(picked));
    e.target.value = "";
  }, [setPickedFiles]);

  const onFolderPicked = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files;
    if (!picked || picked.length === 0) return;
    setPickedFiles(Array.from(picked));
    e.target.value = "";
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
    clearError();
    moveNext();
  }, [currentFile, moveNext, clearError]);

  const handleSubmitAndQueue = useCallback(async () => {
    if (!currentFile) {
      handleError(new Error("请先导入图片"), "请先导入图片");
      return;
    }
    setIsLoading(true);
    clearError();

    try {
      const leftScore = difficultyLeft.trim();
      const rightScore = difficultyRight.trim();
      if ((leftScore && !rightScore) || (!leftScore && rightScore)) {
        handleError(new Error("分数请填写为 a/b（两段都要填）"), "分数格式错误");
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
      handleError(err, "上传失败");
    }

    setIsLoading(false);
  }, [
    clearError,
    convertFileToBase64,
    currentFile,
    customTags,
    difficultyLeft,
    difficultyRight,
    errorTags,
    handleError,
    knowledgeTags,
    moveNext,
    notes,
    questionNo,
    questionType,
    sourceTags,
    subject,
  ]);

  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'column', 'row'], gap: 0, height: '100%' }}>
      {/* Left: Form */}
      <Box
        sx={{
          flex: '1 1 0',
          minWidth: 0,
          pr: [0, 0, 4],
          pb: [4, 4, 0],
          gap: 3,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Box>
          <Heading as="h1" sx={{ fontSize: 4, m: 0 }}>新建题目</Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>上传手稿图片，AI 自动识别并解答</Text>
        </Box>

        <UploadQueue
          files={files}
          index={index}
          isLoading={isLoading}
          remaining={remaining}
          singleInputRef={singleInputRef}
          folderInputRef={folderInputRef}
          onSinglePicked={onSinglePicked}
          onFolderPicked={onFolderPicked}
          onFilesChange={setFiles}
          onIndexChange={setIndex}
        />

        <Box className="oops-card" sx={{ p: 3 }}>
          <AnnotationForm
            subject={subject}
            onSubjectChange={setSubject}
            questionType={questionType}
            onQuestionTypeChange={setQuestionType}
            questionNo={questionNo}
            onQuestionNoChange={setQuestionNo}
            difficultyLeft={difficultyLeft}
            difficultyRight={difficultyRight}
            difficultyLeftRef={difficultyLeftRef}
            difficultyRightRef={difficultyRightRef}
            onDifficultyLeftChange={setDifficultyLeft}
            onDifficultyRightChange={setDifficultyRight}
            notes={notes}
            onNotesChange={setNotes}
            sourceTags={sourceTags}
            onSourceTagsChange={setSourceTags}
            knowledgeTags={knowledgeTags}
            onKnowledgeTagsChange={setKnowledgeTags}
            errorTags={errorTags}
            onErrorTagsChange={setErrorTags}
            customTags={customTags}
            onCustomTagsChange={setCustomTags}
            tagStyles={tagStyles}
            showAdvanced={showAdvanced}
            onShowAdvancedChange={setShowAdvanced}
            onSubmit={handleSubmitAndQueue}
            onSkip={handleSkip}
            isLoading={isLoading}
            hasFile={!!currentFile}
          />
        </Box>
      </Box>

      {/* Right: Image */}
      <Box
        sx={{
          flex: '0 0 50%',
          width: '50%',
          pl: [0, 0, 4],
          pt: [4, 4, 2],
          pb: [0, 0, 2],
          display: ['none', 'none', 'flex'],
          flexDirection: 'column',
          position: "sticky",
          top: "50px",
          height: 'calc(100vh - 100px)',
          alignSelf: "flex-start",
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Text sx={{ fontWeight: 600, fontSize: 2 }}>图片预览</Text>
          {files.length > 0 && (
            <Box className="oops-badge oops-badge-muted">
              {Math.min(index + 1, files.length)} / {files.length}
            </Box>
          )}
        </Box>

        {!currentFile ? (
          <Box
            className="oops-empty-state"
            sx={{
              flex: 1,
              border: '2px dashed',
              borderColor: 'border.default',
              borderRadius: "var(--oops-radius-md)",
              minHeight: 300,
            }}
          >
            <Text as="p" sx={{ fontWeight: 600 }}>等待导入图片</Text>
            <Text as="p" sx={{ fontSize: 1 }}>从左侧选择拍照/多图/文件夹导入</Text>
          </Box>
        ) : (
          <Box className="oops-card" sx={{ overflow: "hidden", flex: 1 }}>
            <ImagePreview file={currentFile} />
          </Box>
        )}
      </Box>
    </Box>
  );
}
