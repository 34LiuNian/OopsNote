"use client";

import { Box, FormControl, Heading, Select, Text } from "@primer/react";
import { PaintbrushIcon } from "@primer/octicons-react";

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
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <PaintbrushIcon size={16} />
        <Box>
          <Text className="oops-section-subtitle">Appearance</Text>
          <Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>
            外观
          </Heading>
        </Box>
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
