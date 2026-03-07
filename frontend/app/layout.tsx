import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { cookies } from "next/headers";
import "./globals.css";
import "katex/dist/katex.min.css";
import { AppLayout, SplashScreen } from '@/components/layout';
import { ThemeProvider, ReactQueryProvider } from '@/components/providers';
import StyledComponentsRegistry from '@/lib/registry';
import { SileoToaster } from '@/components/ui';
import { KatexAutoRender } from '@/components/renderers';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#111827' },
  ],
};

export const metadata: Metadata = {
  title: "OopsNote: AI Mistake Organizer",
  description: "Organize your mistakes problems with AI",
  manifest: '/manifest.webmanifest',
  applicationName: 'OopsNote',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'OopsNote',
  },
  icons: {
    icon: [
      { url: '/icon-light', type: 'image/png', media: '(prefers-color-scheme: light)' },
      { url: '/icon-dark', type: 'image/png', media: '(prefers-color-scheme: dark)' },
      { url: '/icon', type: 'image/png' },
      { url: '/favicon.svg', type: 'image/svg+xml' },
    ],
    apple: [{ url: '/apple-icon', sizes: '180x180', type: 'image/png' }],
  },
};

async function readInitialThemePreference(): Promise<"light" | "dark" | "system"> {
  const store = await cookies();
  const raw = store.get("oopsnote-theme")?.value;
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const initialPreference = await readInitialThemePreference();
  const serverResolved = initialPreference === "light" || initialPreference === "dark" ? initialPreference : undefined;

  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      data-oopsnote-color-scheme={serverResolved}
      style={serverResolved ? ({ colorScheme: serverResolved } as React.CSSProperties) : undefined}
    >
      <head>
        <Script
          id="oopsnote-theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `(function(){\n  try {\n    var key = 'oopsnote-theme';\n    var pref = null;\n\n    // Prefer localStorage, fallback to cookie for SSR alignment.\n    if (window.localStorage) {\n      pref = window.localStorage.getItem(key);\n    }\n    if (pref !== 'light' && pref !== 'dark' && pref !== 'system') {\n      var m = document.cookie.match('(?:^|;\\s*)' + key.replace(/[-.$?*|{}()\\[\\]\\\\/+^]/g, '\\\\$&') + '=([^;]*)');\n      pref = m ? decodeURIComponent(m[1]) : null;\n    }\n\n    var resolved = null;\n    if (pref === 'light' || pref === 'dark') {\n      resolved = pref;\n    } else {\n      resolved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';\n    }\n\n    if (resolved) {\n      var root = document.documentElement;\n      root.dataset.oopsnoteColorScheme = resolved;\n      root.style.colorScheme = resolved;\n      // Ensure initial paint uses the correct system colors.\n      root.style.backgroundColor = 'Canvas';\n      root.style.color = 'CanvasText';\n      if (document.body) {\n        document.body.style.backgroundColor = 'Canvas';\n        document.body.style.color = 'CanvasText';\n      }\n    }\n  } catch (e) {}\n})();`,
          }}
        />
      </head>
      <body style={{ backgroundColor: "Canvas", color: "CanvasText" }}>
        <SplashScreen />
        <StyledComponentsRegistry>
          <ReactQueryProvider>
            <ThemeProvider initialPreference={initialPreference}>
              <KatexAutoRender />
              <SileoToaster />
              <AppLayout>
                {children}
              </AppLayout>
            </ThemeProvider>
          </ReactQueryProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}
