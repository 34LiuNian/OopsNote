"use client";

import { useCallback, useState, useRef } from "react";
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

const DEFAULT_SUBJECT = "math";

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
    <Box sx={{ display: 'flex', flexDirection: ['column', 'column', 'row'], gap: 4, height: '100%' }}>
      {/* Left: Form */}
      <Box
        sx={{
          width: '100%',
          maxWidth: '480px',
          flexShrink: 0,
          pr: [0, 0, 4],
          pb: [4, 4, 0],
        }}
      >
        <Box sx={{ mb: 3 }}>
          <Heading as="h1" sx={{ fontSize: 4, mb: 1 }}>新建题目</Heading>
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
          <Heading as="h2" sx={{ fontSize: 3 }}>图片预览</Heading>
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
          <ImagePreview file={currentFile} />
        )}
      </Box>
    </Box>
  );
}
