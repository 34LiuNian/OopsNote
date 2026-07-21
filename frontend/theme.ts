import { createTheme, type MantineThemeOverride } from "@mantine/core";

const graphite = [
  "#fafafa",
  "#f4f4f5",
  "#e4e4e7",
  "#d4d4d8",
  "#a1a1aa",
  "#71717a",
  "#52525b",
  "#3f3f46",
  "#27272a",
  "#18181b",
] as const;

export const oopsTheme: MantineThemeOverride = createTheme({
  primaryColor: "graphite",
  primaryShade: { light: 9, dark: 8 },
  colors: { graphite },
  fontFamily: "Inter, Noto Sans SC, HarmonyOS Sans, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
  fontFamilyMonospace: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
  headings: {
    fontFamily: "Inter, Noto Sans SC, HarmonyOS Sans, system-ui, sans-serif",
    fontWeight: "650",
  },
  defaultRadius: "md",
  radius: {
    xs: "4px",
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "16px",
  },
  spacing: {
    xs: "4px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "24px",
  },
  shadows: {
    xs: "0 1px 2px rgb(15 23 42 / 0.04)",
    sm: "0 1px 3px rgb(15 23 42 / 0.07)",
    md: "0 8px 24px rgb(15 23 42 / 0.08)",
    lg: "0 16px 40px rgb(15 23 42 / 0.12)",
    xl: "0 24px 64px rgb(15 23 42 / 0.16)",
  },
  components: {
    Button: {
      defaultProps: {
        radius: "sm",
      },
    },
    ActionIcon: {
      defaultProps: {
        radius: "sm",
      },
    },
    TextInput: {
      defaultProps: {
        radius: "md",
      },
    },
    Textarea: {
      defaultProps: {
        radius: "md",
      },
    },
    Select: {
      defaultProps: {
        radius: "md",
      },
    },
  },
});
