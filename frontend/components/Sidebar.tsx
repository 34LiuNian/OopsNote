"use client";

import { usePathname } from "next/navigation";
import { Box, NavList, Text } from "@primer/react";
import { 
  PlusIcon, 
  RepoIcon, 
  TagIcon, 
  GearIcon, 
  BookIcon 
} from "@primer/octicons-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "新建题目", icon: PlusIcon },
  { href: "/library", label: "题库", icon: RepoIcon },
  { href: "/tags", label: "标签管理", icon: TagIcon },
  { href: "/settings", label: "设置", icon: GearIcon },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <Box
      as="aside"
      sx={{
        width: ["100%", 240],
        bg: "canvas.default",
        borderRight: ["none", "1px solid"],
        borderBottom: ["1px solid", "none"],
        borderColor: "border.default",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        position: ["relative", "sticky"],
        top: 0,
        height: ["auto", "100vh"],
        overflowY: ["visible", "auto"],
      }}
    >
      <Box
        as={Link}
        href="/"
        sx={{
          px: 3,
          py: 2,
          display: "flex",
          alignItems: "center",
          gap: 2,
          textDecoration: "none",
          color: "fg.default",
          borderBottom: "1px solid",
          borderColor: "border.default",
        }}
      >
        <BookIcon size={16} />
        <Text sx={{ fontWeight: "bold", fontSize: 2 }}>OopsNote</Text>
      </Box>

      <NavList sx={{ px: 2, py: 2 }}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <NavList.Item 
              key={item.href} 
              href={item.href} 
              aria-current={active ? "page" : undefined}
              as={Link}
            >
              <NavList.LeadingVisual>
                <item.icon />
              </NavList.LeadingVisual>
              {item.label}
            </NavList.Item>
          );
        })}
      </NavList>
    </Box>
  );
}
