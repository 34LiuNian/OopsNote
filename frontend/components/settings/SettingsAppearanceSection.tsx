"use client";

import { Box, Heading, Text } from "@/components/ui/primitives";
import { PaintbrushIcon } from "@/components/ui/icons";

type SettingsAppearanceSectionProps = {
  resolvedTheme: "light" | "dark";
};

export function SettingsAppearanceSection({
  resolvedTheme,
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

      <Text sx={{ color: "fg.muted", fontSize: 1 }}>
        跟随系统（当前：{resolvedTheme === "dark" ? "暗色" : "亮色"}）
      </Text>
    </Box>
  );
}
