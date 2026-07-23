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

// This must run before Next chunks because an old PWA worker can cache those chunks.
const devServiceWorkerCleanup = `(function(){try{if(!('serviceWorker' in navigator))return;var marker='oopsnote-dev-sw-cleanup';var isAppWorker=function(worker){if(!worker)return false;try{var url=new URL(worker.scriptURL,location.href);return url.origin===location.origin&&url.pathname==='/sw.js';}catch(e){return false;}};var controller=navigator.serviceWorker.controller;var hadController=isAppWorker(controller);var cacheNames=['start-url','google-fonts-webfonts','google-fonts-stylesheets','static-font-assets','static-image-assets','next-static-js-assets','next-image','static-audio-assets','static-video-assets','static-js-assets','static-style-assets','next-data','static-data-assets','apis','pages-rsc-prefetch','pages-rsc','pages','cross-origin'];navigator.serviceWorker.getRegistrations().then(function(items){var appItems=items.filter(function(item){return isAppWorker(item.active)||isAppWorker(item.waiting)||isAppWorker(item.installing);});if(!hadController&&!appItems.length){sessionStorage.removeItem(marker);return;}var removeCaches=('caches' in window)?caches.keys().then(function(keys){return Promise.all(keys.filter(function(key){return key.indexOf('workbox-precache')===0||cacheNames.indexOf(key)>=0;}).map(function(key){return caches.delete(key);}));}):Promise.resolve();return Promise.all([Promise.all(appItems.map(function(item){return item.unregister();})),removeCaches]).then(function(){if(hadController&&sessionStorage.getItem(marker)!=='reloading'){sessionStorage.setItem(marker,'reloading');location.reload();return;}sessionStorage.removeItem(marker);});}).catch(function(){sessionStorage.removeItem(marker);});}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <link rel="stylesheet" href="/vendor/tikzjax/css/fonts.css" />
        <Script id="oopsnote-theme-init" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: systemThemeInit }} />
        {process.env.NODE_ENV === "development" && (
          <script
            id="oopsnote-dev-sw-cleanup"
            dangerouslySetInnerHTML={{ __html: devServiceWorkerCleanup }}
          />
        )}
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
