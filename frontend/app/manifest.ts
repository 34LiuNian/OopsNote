import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OopsNote",
    short_name: "OopsNote",
    description: "Organize your mistakes problems with AI",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    lang: "zh-CN",
    icons: [
      {
        src: "/favicon.svg",
        type: "image/svg+xml",
        sizes: "any",
      },
    ],
  };
}