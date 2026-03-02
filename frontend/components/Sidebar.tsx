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
  SidebarCollapseIcon,
  SidebarExpandIcon,
} from "@primer/octicons-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "新建题目", icon: PlusIcon, section: "main" },
  { href: "/library", label: "题库", icon: RepoIcon, section: "main" },
  { href: "/paper-builder", label: "组卷", icon: ChecklistIcon, section: "main" },
  { href: "/tags", label: "标签管理", icon: TagIcon, section: "manage" },
  { href: "/settings", label: "设置", icon: GearIcon, section: "manage" },
  { href: "/debug", label: "Debug", icon: BookIcon, section: "manage" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const mainItems = NAV_ITEMS.filter((i) => i.section === "main");
  const manageItems = NAV_ITEMS.filter((i) => i.section === "manage");

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <Box
      as="aside"
      sx={{
        width: collapsed ? ["100%", 56] : ["100%", 220],
        bg: "canvas.subtle",
        borderRight: ["none", "1px solid"],
        borderRightColor: ["border.muted", "border.muted"],
        borderBottom: ["1px solid", "none"],
        borderBottomColor: ["border.muted", "none"],
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        position: ["relative", "sticky"],
        top: 0,
        height: ["auto", "100vh"],
        overflowY: ["visible", "auto"],
        overflowX: "hidden",
        transition: "width var(--oops-transition-normal)",
      }}
    >
      {/* Logo area */}
      <Box
        onClick={() => setCollapsed(!collapsed)}
        sx={{
          px: collapsed ? 0 : 3,
          py: 3,
          display: "flex",
          alignItems: "center",
          gap: 2,
          textDecoration: "none",
          color: "fg.default",
          height: 50,
          cursor: "pointer",
          justifyContent: collapsed ? "center" : "flex-start",
          borderBottom: "1px solid",
          borderColor: "border.muted",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", height: 32 }}>
          {collapsed ? <ThreeBarsIcon size={28} /> : <RepoIcon size={28} />}
        </Box>
        {!collapsed && (
          <Text sx={{ fontWeight: "bold", fontSize: 5, lineHeight: 1, height: 32, display: "flex", alignItems: "center", fontFamily: "'OopsNoteFont', 'Inter', 'HarmonyOS Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>OopsNote</Text>
        )}
      </Box>

      {/* Main nav */}
      <Box sx={{ flex: 1, py: 2 }}>
        {collapsed ? (
          <Box sx={{ display: "flex", flexDirection: "column", gap: "2px", px: 1 }}>
            {[...mainItems, ...manageItems].map((item) => {
              const active = isActive(item.href);
              return (
                <Box key={item.href} sx={{ display: "flex", justifyContent: "center" }}>
                  <IconButton
                    as={Link}
                    href={item.href}
                    icon={item.icon}
                    aria-label={item.label}
                    variant={active ? "default" : "invisible"}
                    sx={{ borderRadius: "var(--oops-radius-sm)" }}
                  />
                </Box>
              );
            })}
          </Box>
        ) : (
          <>
            <NavList sx={{ px: "6px" }}>
              {mainItems.map((item) => {
                const active = isActive(item.href);
                return (
                  <Box key={item.href} sx={{ my: "1px" }}>
                    <NavList.Item
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      as={Link}
                      sx={{
                        whiteSpace: "nowrap",
                        borderRadius: "var(--oops-radius-sm)",
                        transition: "background-color var(--oops-transition-fast)",
                        px: 2,
                      }}
                    >
                      <NavList.LeadingVisual>
                        <item.icon />
                      </NavList.LeadingVisual>
                      {item.label}
                    </NavList.Item>
                  </Box>
                );
              })}
            </NavList>

            {/* Divider */}
            <Box sx={{ mx: 3, my: 2, borderTop: "1px solid", borderColor: "border.muted" }} />

            <Text
              sx={{
                fontSize: "11px",
                fontWeight: 600,
                color: "fg.muted",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                px: 3,
                mb: 1,
                display: "block",
              }}
            >
              管理
            </Text>

            <NavList sx={{ px: "6px" }}>
              {manageItems.map((item) => {
                const active = isActive(item.href);
                return (
                  <Box key={item.href} sx={{ my: "1px" }}>
                    <NavList.Item
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      as={Link}
                      sx={{
                        whiteSpace: "nowrap",
                        borderRadius: "var(--oops-radius-sm)",
                        transition: "background-color var(--oops-transition-fast)",
                        px: 2,
                      }}
                    >
                      <NavList.LeadingVisual>
                        <item.icon />
                      </NavList.LeadingVisual>
                      {item.label}
                    </NavList.Item>
                  </Box>
                );
              })}
            </NavList>
          </>
        )}
      </Box>

      {/* Collapse toggle at bottom */}
      <Box
        onClick={() => setCollapsed(!collapsed)}
        sx={{
          px: collapsed ? 0 : 3,
          py: 2,
          display: "flex",
          alignItems: "center",
          justifyContent: collapsed ? "center" : "flex-end",
          cursor: "pointer",
          color: "fg.muted",
          borderTop: "1px solid",
          borderColor: "border.muted",
          "&:hover": { color: "fg.default" },
          transition: "color var(--oops-transition-fast)",
        }}
      >
        {collapsed ? <SidebarExpandIcon size={16} /> : <SidebarCollapseIcon size={16} />}
      </Box>
    </Box>
  );
}
