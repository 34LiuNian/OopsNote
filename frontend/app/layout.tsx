import type { Metadata } from "next";
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <StyledComponentsRegistry>
          <ThemeProvider>
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
