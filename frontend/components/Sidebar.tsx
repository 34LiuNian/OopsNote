"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Box, NavList, Text, IconButton } from "@primer/react";
import {
  PlusIcon,
  RepoIcon,
  TagIcon,
  GearIcon,
  BookIcon,
  ChecklistIcon,
  ThreeBarsIcon,
  XIcon
} from "@primer/octicons-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "新建题目", icon: PlusIcon },
  { href: "/library", label: "题库", icon: RepoIcon },
  { href: "/paper-builder", label: "组卷", icon: ChecklistIcon },
  { href: "/tags", label: "标签管理", icon: TagIcon },
  { href: "/settings", label: "设置", icon: GearIcon },
  { href: "/debug", label: "Debug 页面", icon: BookIcon },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <Box
      as="aside"
      sx={{
        width: collapsed ? ["100%", 64] : ["100%", 200],
        bg: "canvas.default",
        borderRight: ["none", "1px solid"],
        borderRightColor: ["border.muted", "border.muted"],
        borderBottom: ["1px solid", "none"],
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        position: ["relative", "sticky"],
        top: 0,
        height: ["auto", "100vh"],
        overflowY: ["visible", "auto"],
        transition: "width 0.2s ease-in-out",
      }}
    >
      <Box
        onClick={() => setCollapsed(!collapsed)}
        sx={{
          px: collapsed ? 0 : 3,
          py: 2,
          display: "flex",
          alignItems: "center",
          gap: 3,
          textDecoration: "none",
          color: "fg.default",
          height: 56,
          cursor: "pointer",
          justifyContent: collapsed ? "center" : "flex-start",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", height: 32 }}>
          {collapsed ? <ThreeBarsIcon size={28} /> : <RepoIcon size={28} />}
        </Box>
        {!collapsed && (
          <Text sx={{ fontWeight: "bold", fontSize: 5, lineHeight: 1, height: 32, display: "flex", alignItems: "center", fontFamily: "'OopsNoteFont', 'Inter', 'HarmonyOS Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>OopsNote</Text>
        )}
      </Box>

      <NavList sx={{ px: 2 }}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Box key={item.href} sx={{ my: "2px" }}>
              <NavList.Item
                href={item.href}
                aria-current={active ? "page" : undefined}
                as={Link}
                title={collapsed ? item.label : undefined}
                sx={{
                  whiteSpace: 'nowrap',
                }}
              >
                <NavList.LeadingVisual>
                  <item.icon />
                </NavList.LeadingVisual>
                {!collapsed && item.label}
              </NavList.Item>
            </Box>
          );
        })}
      </NavList>
    </Box>
  );
}
