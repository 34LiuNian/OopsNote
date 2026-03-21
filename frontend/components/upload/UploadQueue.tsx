"use client";

import { useCallback, useEffect, useState } from "react";
import { Box, Button, Checkbox, Label, Text } from "@primer/react";

type UploadQueueProps = {
  files: File[];
  index: number;
  isLoading: boolean;
  remaining?: number;
  autoRecognize: boolean;
  singleInputRef: React.RefObject<HTMLInputElement>;
  folderInputRef: React.RefObject<HTMLInputElement>;
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
      sx={{
        display: 'flex',
        gap: 2,
        alignItems: 'center',
        flexWrap: 'wrap',
        p: 2,
        border: '1px dashed',
        borderColor: isDragOver ? 'accent.fg' : 'border.default',
        borderRadius: "var(--oops-radius-sm)",
        bg: isDragOver ? 'accent.subtle' : 'canvas.default',
        transition: 'all var(--oops-transition-fast)',
      }}
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
      <Button
        variant="primary"
        onClick={() => singleInputRef.current?.click()}
        disabled={isLoading}
      >
        拍照 / 选择图片
      </Button>
      <Button
        onClick={() => folderInputRef.current?.click()}
        disabled={isLoading}
        variant="invisible"
      >
        导入文件夹
      </Button>
      {files.length > 0 && (
        <Box className="oops-badge oops-badge-accent">
          剩余 {remainingCount} / {files.length}
        </Box>
      )}
      <Label sx={{ color: 'fg.muted', fontWeight: 400 }}>
        或拖拽图片到这里
      </Label>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, ml: ['0', 'auto'] }}>
        <Checkbox
          checked={autoRecognize}
          onChange={(event) => onAutoRecognizeChange(event.target.checked)}
          disabled={isLoading}
        />
        <Text sx={{ fontSize: 1, color: 'fg.muted' }}>导入后自动识别并入队</Text>
      </Box>
    </Box>
  );
}
