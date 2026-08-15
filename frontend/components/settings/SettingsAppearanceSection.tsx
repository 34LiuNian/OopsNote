"use client";

import { Box, Heading, Text } from "@/components/ui/primitives";
import { PaintbrushIcon } from "@/components/ui/icons";
import sxStyles from "./SettingsAppearanceSection.sx.module.css";

type SettingsAppearanceSectionProps = {
  resolvedTheme: "light" | "dark";
};

export function SettingsAppearanceSection({
  resolvedTheme,
}: SettingsAppearanceSectionProps) {
  return (
    <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx2}>
        <PaintbrushIcon size={16} />
        <Box>
          <Text className="oops-section-subtitle">Appearance</Text>
          <Heading as="h3" className={["oops-section-title", sxStyles.sx3].filter(Boolean).join(" ")} >
            外观
          </Heading>
        </Box>
      </Box>

      <Text className={sxStyles.sx4}>
        跟随系统（当前：{resolvedTheme === "dark" ? "暗色" : "亮色"}）
      </Text>
    </Box>
  );
}
