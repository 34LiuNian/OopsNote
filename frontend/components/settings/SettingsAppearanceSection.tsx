"use client";

import { Box, FormControl, Heading, Select, Text } from "@primer/react";

type SettingsAppearanceSectionProps = {
  preference: "system" | "light" | "dark";
  resolvedTheme: "light" | "dark";
  onChangePreference: (next: "system" | "light" | "dark") => void;
};

export function SettingsAppearanceSection({
  preference,
  resolvedTheme,
  onChangePreference,
}: SettingsAppearanceSectionProps) {
  return (
    <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
      <Box sx={{ mb: 3 }}>
        <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Appearance</Text>
        <Heading as="h2" sx={{ fontSize: 3 }}>
          外观
        </Heading>
      </Box>

      <FormControl>
        <FormControl.Label>主题</FormControl.Label>
        <Select
          value={preference}
          onChange={(e) => onChangePreference(e.target.value as "system" | "light" | "dark")}
          block
        >
          <Select.Option value="system">跟随系统（当前：{resolvedTheme === "dark" ? "暗色" : "亮色"}）</Select.Option>
          <Select.Option value="light">亮色</Select.Option>
          <Select.Option value="dark">暗色</Select.Option>
        </Select>
        <FormControl.Caption>选择“跟随系统”会在系统主题变化时自动切换。</FormControl.Caption>
      </FormControl>
    </Box>
  );
}
