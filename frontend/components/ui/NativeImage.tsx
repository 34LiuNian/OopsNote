import { forwardRef, type ComponentPropsWithoutRef } from "react";

/**
 * Browser-native image boundary for transient uploads and geometry-controlled
 * canvases. These images may be Blob URLs, or their intrinsic dimensions and
 * percentage transforms are part of an interaction contract, so Next Image's
 * optimizer/layout wrapper is not interchangeable here.
 */
type NativeImageProps = ComponentPropsWithoutRef<"img"> & { alt: string };

export const NativeImage = forwardRef<HTMLImageElement, NativeImageProps>(
  ({ alt, ...props }, ref) => {
  // eslint-disable-next-line @next/next/no-img-element -- intentional native-image boundary documented above
    return <img {...props} ref={ref} alt={alt} />;
  },
);

NativeImage.displayName = "NativeImage";
