import type { Metadata } from "next";
import Script from "next/script";
import { cookies } from "next/headers";
import "./globals.css";
import "katex/dist/katex.min.css";
import AppLayout from '@/components/AppLayout';
import { ThemeProvider } from '@/components/ThemeProvider';
import StyledComponentsRegistry from '@/lib/registry';
import { KatexAutoRender } from '@/components/KatexAutoRender';

export const metadata: Metadata = {
  title: "AI Mistake Organizer",
  description: "Organize your mistakes with AI",
};

function readInitialThemePreference(): "light" | "dark" | "system" {
  const raw = cookies().get("oopsnote-theme")?.value;
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const initialPreference = readInitialThemePreference();
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
            __html: `(function(){\n  try {\n    var key = 'oopsnote-theme';\n    var pref = null;\n\n    // Prefer localStorage, fallback to cookie for SSR alignment.
    if (window.localStorage) {\n      pref = window.localStorage.getItem(key);\n    }\n    if (pref !== 'light' && pref !== 'dark' && pref !== 'system') {\n      var m = document.cookie.match('(?:^|;\\s*)' + key.replace(/[-.$?*|{}()\\[\\]\\\\/+^]/g, '\\\\$&') + '=([^;]*)');\n      pref = m ? decodeURIComponent(m[1]) : null;\n    }\n\n    var resolved = null;\n    if (pref === 'light' || pref === 'dark') {\n      resolved = pref;\n    } else {\n      resolved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';\n    }\n\n    if (resolved) {\n      var root = document.documentElement;\n      root.dataset.oopsnoteColorScheme = resolved;\n      root.style.colorScheme = resolved;\n      // Ensure initial paint uses the correct system colors.
      root.style.backgroundColor = 'Canvas';\n      root.style.color = 'CanvasText';\n      if (document.body) {\n        document.body.style.backgroundColor = 'Canvas';\n        document.body.style.color = 'CanvasText';\n      }\n    }\n  } catch (e) {}\n})();`,
          }}
        />
      </head>
      <body>
        <StyledComponentsRegistry>
          <ThemeProvider initialPreference={initialPreference}>
            <KatexAutoRender />
            <AppLayout>
              {children}
            </AppLayout>
          </ThemeProvider>
        </StyledComponentsRegistry>
      </body>
    </html>
  );
}
