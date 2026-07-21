"use client";

import { useEffect, useState } from "react";
import { Box } from "@/components/ui/primitives";

export function ImagePreview({ file }: { file: File }) {
  const [url, setUrl] = useState("");

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  return <Box className="capture-image-preview">{url && <img src={url} alt={file.name} draggable={false} />}</Box>;
}
