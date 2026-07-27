"use client";

import { useEffect, useRef } from "react";
import { Box } from "@/components/ui/primitives";
import { NativeImage } from "@/components/ui/NativeImage";

export function ImagePreview({ file }: { file: File }) {
  const imageRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    if (imageRef.current) imageRef.current.src = nextUrl;
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  return <Box className="capture-image-preview"><NativeImage ref={imageRef} alt={file.name} draggable={false} /></Box>;
}
