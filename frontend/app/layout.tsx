import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";
import "katex/dist/katex.min.css";
import "@mantine/core/styles.css";
import { AppLayout, SplashScreen } from "@/components/layout";
import { ThemeProvider, ReactQueryProvider } from "@/components/providers";
import { SileoToaster } from "@/components/ui";
import { KatexAutoRender } from "@/components/renderers";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#18181b" },
  ],
};

export const metadata: Metadata = {
  title: "OopsNote: AI Mistake Organizer",
  description: "Organize your mistakes problems with AI",
  manifest: "/manifest.webmanifest",
  applicationName: "OopsNote",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "OopsNote",
  },
  icons: {
    icon: [
      { url: "/icon-light", type: "image/png", media: "(prefers-color-scheme: light)" },
      { url: "/icon-dark", type: "image/png", media: "(prefers-color-scheme: dark)" },
      { url: "/icon", type: "image/png" },
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-icon", sizes: "180x180", type: "image/png" }],
  },
};

const systemThemeInit = `(function(){try{var dark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;var resolved=dark?'dark':'light';var root=document.documentElement;root.dataset.oopsnoteColorScheme=resolved;root.dataset.mantineColorScheme=resolved;root.style.colorScheme=resolved;root.style.backgroundColor='Canvas';root.style.color='CanvasText';}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <link rel="stylesheet" href="/vendor/tikzjax/css/fonts.css" />
        <Script id="oopsnote-theme-init" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: systemThemeInit }} />
      </head>
      <body style={{ backgroundColor: "Canvas", color: "CanvasText" }}>
        <SplashScreen />
        <ReactQueryProvider>
          <ThemeProvider initialPreference="system">
            <KatexAutoRender />
            <SileoToaster />
            <AppLayout>{children}</AppLayout>
          </ThemeProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
