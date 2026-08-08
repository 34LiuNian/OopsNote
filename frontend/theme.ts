import { createTheme, type MantineThemeOverride } from "@mantine/core";

const graphite = [
  "var(--oops-graphite-0)",
  "var(--oops-graphite-1)",
  "var(--oops-graphite-2)",
  "var(--oops-graphite-3)",
  "var(--oops-graphite-4)",
  "var(--oops-graphite-5)",
  "var(--oops-graphite-6)",
  "var(--oops-graphite-7)",
  "var(--oops-graphite-8)",
  "var(--oops-graphite-9)",
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
    xs: "var(--oops-radius-xs)",
    sm: "var(--oops-radius-sm)",
    md: "var(--oops-radius-md)",
    lg: "var(--oops-radius-lg)",
    xl: "var(--oops-radius-shell)",
  },
  spacing: {
    xs: "var(--oops-space-1)",
    sm: "var(--oops-space-2)",
    md: "var(--oops-space-3)",
    lg: "var(--oops-space-4)",
    xl: "var(--oops-space-5)",
  },
  shadows: {
    xs: "var(--oops-shadow-sm)",
    sm: "var(--oops-shadow-sm)",
    md: "var(--oops-shadow-md)",
    lg: "var(--oops-shadow-lg)",
    xl: "var(--oops-shadow-float)",
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
