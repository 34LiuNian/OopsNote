"use client";

import type { CSSProperties, ReactNode } from "react";
import { NativeImage } from "@/components/ui/NativeImage";

type ImageSelectionStageProps = {
  src?: string;
  alt: string;
  children: ReactNode;
  layout?: "intrinsic" | "fixed";
  tone?: "original" | "auto" | "inverted";
  className?: string;
  style?: CSSProperties;
  imageStyle?: CSSProperties;
  fallback?: ReactNode;
};

/**
 * Owns the rendered image boundary shared by image/PDF annotation tools.
 * Annotation children always receive exactly the same grid area as the image;
 * they must not infer media geometry from an outer viewport or toolbar.
 */
export function ImageSelectionStage({
  src,
  alt,
  children,
  layout = "intrinsic",
  tone = "original",
  className,
  style,
  imageStyle,
  fallback,
}: ImageSelectionStageProps) {
  const classes = [
    "image-selection-stage",
    `is-${layout}`,
    `is-tone-${tone}`,
    className ?? "",
  ].filter(Boolean).join(" ");

  return (
    <div className={classes} style={style}>
      {src ? (
        <NativeImage
          className="image-selection-stage__media"
          src={src}
          alt={alt}
          draggable={false}
          style={imageStyle}
        />
      ) : (
        <div className="image-selection-stage__fallback">{fallback}</div>
      )}
      <div className="image-selection-stage__annotation">{children}</div>
    </div>
  );
}
