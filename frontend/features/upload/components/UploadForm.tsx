"use client";

import { useCallback, useState, useRef, useEffect } from "react";
import { Box, Heading, Text } from "@primer/react";
import { useTagDimensions } from "@/features/tags";
import { useApiError } from "@/hooks/useApiError";
import { createUploadTaskAndProcess } from "../api";
import { ImagePreview, type ImagePreviewHandle } from "@/components/upload/ImagePreview";
import { notify } from "@/lib/notify";
import { AnnotationForm } from "@/components/upload/AnnotationForm";
import { UploadQueue } from "@/components/upload/UploadQueue";

const DEFAULT_SUBJECT = "auto";

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
  const [autoRecognize, setAutoRecognize] = useState(false);
  const [autoRecognizedKey, setAutoRecognizedKey] = useState("");
  const { error, handleError, clearError } = useApiError({
    defaultFallback: "上传失败，请稍后重试",
  });

  const singleInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const difficultyLeftRef = useRef<HTMLInputElement>(null);
  const difficultyRightRef = useRef<HTMLInputElement>(null);
  const imagePreviewRef = useRef<ImagePreviewHandle | null>(null);

  const currentFile = files[index] ?? null;
  const remaining = files.length - index;

  useEffect(() => {
    console.log('[UploadForm] index 变化:', { index, filesLength: files.length, hasRef: !!difficultyLeftRef.current });
    if (files.length > 0 && index < files.length) {
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
      notify.success({ title: `已导入 ${images.length} 张图片` });
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

  const convertFileToBase64 = useCallback(async (input: Blob): Promise<string> => {
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

  const optimizeImageBlob = useCallback(async (input: Blob): Promise<Blob> => {
    const bitmap = await createImageBitmap(input);
    try {
      const maxSide = 2200;
      const ratio = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
      const targetWidth = Math.max(1, Math.round(bitmap.width * ratio));
      const targetHeight = Math.max(1, Math.round(bitmap.height * ratio));

      const canvas = document.createElement("canvas");
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      const context = canvas.getContext("2d");
      if (!context) {
        return input;
      }
      context.drawImage(bitmap, 0, 0, targetWidth, targetHeight);

      const output = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.86);
      });
      return output ?? input;
    } finally {
      bitmap.close();
    }
  }, []);

  const moveNext = useCallback(() => {
    setIndex((prev) => prev + 1);
  }, []);

  const handleSkip = useCallback(() => {
    if (!currentFile) return;
      notify.info({ title: "已跳过，进入下一张" });
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

      const edited = await imagePreviewRef.current?.exportImage();
      const sourceBlob = edited?.blob ?? currentFile;
      const optimizedBlob = await optimizeImageBlob(sourceBlob);
      const imageBase64 = await convertFileToBase64(optimizedBlob);

      const payload = {
        subject,
        notes,
        question_no: questionNo.trim() || undefined,
        source: sourceTags.length > 0 ? sourceTags[0] : undefined,
        question_type: questionType || undefined,
        difficulty: difficultyValue,
        knowledge_tags: knowledgeTags,
        error_tags: errorTags,
        user_tags: customTags,
        image_base64: imageBase64,
        filename: currentFile.name,
        mime_type: optimizedBlob.type || currentFile.type || "image/png",
      };

      const data = await createUploadTaskAndProcess(payload);
      const id = data.task.id;

      setLastTaskId(id);
        notify.success({
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
    optimizeImageBlob,
  ]);

  useEffect(() => {
    if (!autoRecognize || !currentFile || isLoading) {
      return;
    }
    const key = `${currentFile.name}_${currentFile.size}_${index}`;
    if (autoRecognizedKey === key) {
      return;
    }
    setAutoRecognizedKey(key);
    void handleSubmitAndQueue();
  }, [autoRecognize, autoRecognizedKey, currentFile, handleSubmitAndQueue, index, isLoading]);

  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'column', 'row'], gap: 0, height: '100%' }}>
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
          autoRecognize={autoRecognize}
          singleInputRef={singleInputRef}
          folderInputRef={folderInputRef}
          onSinglePicked={onSinglePicked}
          onFolderPicked={onFolderPicked}
          onFilesDropped={setPickedFiles}
          onFilesChange={setFiles}
          onIndexChange={setIndex}
          onAutoRecognizeChange={setAutoRecognize}
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
            <ImagePreview ref={imagePreviewRef} file={currentFile} />
          </Box>
        )}
      </Box>
    </Box>
  );
}