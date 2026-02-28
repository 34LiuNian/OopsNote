"use client";

import { useEffect } from "react";
import { Box, Button, Label } from "@primer/react";
import { sileo } from "sileo";

type UploadQueueProps = {
  files: File[];
  index: number;
  isLoading: boolean;
  remaining?: number;
  singleInputRef: React.RefObject<HTMLInputElement>;
  folderInputRef: React.RefObject<HTMLInputElement>;
  onSinglePicked: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFolderPicked: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFilesChange: (files: File[]) => void;
  onIndexChange: (index: number) => void;
};

export function UploadQueue({
  files,
  index,
  isLoading,
  remaining,
  singleInputRef,
  folderInputRef,
  onSinglePicked,
  onFolderPicked,
  onFilesChange,
  onIndexChange,
}: UploadQueueProps) {
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

  return (
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
        <Label variant="secondary">剩余 {remainingCount} / {files.length}</Label>
      )}
    </Box>
  );
}
