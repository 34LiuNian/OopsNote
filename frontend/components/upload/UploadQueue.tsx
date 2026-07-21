"use client";

import { useCallback, useEffect, useState } from "react";
import { Box, Button, Text } from "@/components/ui/primitives";
import { FolderOpenIcon, ImageIcon, UploadIcon } from "@/components/ui/icons";

type UploadQueueProps = {
  files: File[];
  index: number;
  isLoading: boolean;
  remaining?: number;
  autoRecognize: boolean;
  singleInputRef: React.RefObject<HTMLInputElement | null>;
  folderInputRef: React.RefObject<HTMLInputElement | null>;
  onSinglePicked: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFolderPicked: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFilesDropped: (files: File[]) => void;
  onFilesChange: (files: File[]) => void;
  onIndexChange: (index: number) => void;
  onAutoRecognizeChange: (value: boolean) => void;
};

export function UploadQueue({
  files,
  index,
  isLoading,
  remaining,
  autoRecognize,
  singleInputRef,
  folderInputRef,
  onSinglePicked,
  onFolderPicked,
  onFilesDropped,
  onFilesChange,
  onIndexChange,
  onAutoRecognizeChange,
}: UploadQueueProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const remainingCount = remaining ?? (files.length - index);

  // Enable folder import on Chromium browsers.
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
    // Prefer camera on mobile when available.
    if (singleInputRef.current) {
      singleInputRef.current.setAttribute('capture', 'environment');
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length === 0) return;
    onFilesDropped(dropped);
  }, [onFilesDropped]);

  return (
    <Box
      className={`capture-dropzone${isDragOver ? " is-dragging" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
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
      <Box className="capture-dropzone__icon" aria-hidden="true">
        <ImageIcon size={20} />
      </Box>
      <Box className="capture-dropzone__body">
        <Text className="capture-dropzone__title">导入题目图片</Text>
        <Text className="capture-dropzone__hint">支持多选、拖放或相册拍照</Text>
      </Box>
      <Box className="capture-dropzone__actions">
        <Button variant="primary" onClick={() => singleInputRef.current?.click()} disabled={isLoading}>
          <UploadIcon size={16} />
          选择图片
        </Button>
        <Button onClick={() => folderInputRef.current?.click()} disabled={isLoading} variant="invisible">
          <FolderOpenIcon size={16} />
          文件夹
        </Button>
      </Box>
      <Box className="capture-dropzone__footer">
        {files.length > 1 ? (
          <Box className="capture-file-navigation">
            <button type="button" onClick={() => onIndexChange(Math.max(0, index - 1))} disabled={isLoading || index === 0}>上一张</button>
            <Text>{index + 1} / {files.length}</Text>
            <button type="button" onClick={() => onIndexChange(Math.min(files.length - 1, index + 1))} disabled={isLoading || index === files.length - 1}>下一张</button>
          </Box>
        ) : files.length > 0 ? (
          <Box className="oops-badge oops-badge-muted">待处理 {remainingCount} / {files.length}</Box>
        ) : <span />}
        <label className="capture-auto-recognize">
          <input
            className="capture-auto-recognize__input"
            type="checkbox"
          checked={autoRecognize}
          onChange={(event) => onAutoRecognizeChange(event.target.checked)}
          disabled={isLoading}
          />
          <Text>导入后自动入队</Text>
        </label>
      </Box>
    </Box>
  );
}
