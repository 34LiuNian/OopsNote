"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Text } from "@/components/ui/primitives";
import {
  PlusIcon,
  RepoIcon,
  BookIcon,
  ChecklistIcon,
  ScanIcon,
  SidebarCollapseIcon,
  SidebarExpandIcon,
} from "@/components/ui/icons";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "新建题目", icon: PlusIcon, section: "main" },
  { href: "/batch-segment", label: "批量扫描", icon: ScanIcon, section: "main" },
  { href: "/library", label: "题库", icon: RepoIcon, section: "main" },
  { href: "/paper-builder", label: "组卷", icon: ChecklistIcon, section: "main" },
  { href: "/debug", label: "渲染调试", icon: BookIcon, section: "tools" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const mainItems = NAV_ITEMS.filter((i) => i.section === "main");
  const toolItems = NAV_ITEMS.filter((i) => i.section === "tools");

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside className={`app-sidebar oops-desktop-sidebar${collapsed ? " is-collapsed" : ""}`}>
      <button
        className="app-sidebar__brand"
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
      >
        <span className="app-sidebar__mark" aria-hidden="true" />
        {!collapsed && <Text>OopsNote</Text>}
      </button>

      <nav className="app-sidebar__nav" aria-label="主导航">
        {mainItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link key={item.href} href={item.href} className={`app-sidebar__link${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined}>
              <item.icon size={17} strokeWidth={1.9} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}

        <div className="app-sidebar__divider" />
        {!collapsed && <span className="app-sidebar__label">工具</span>}

        {toolItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link key={item.href} href={item.href} className={`app-sidebar__link${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined}>
              <item.icon size={17} strokeWidth={1.9} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <button className="app-sidebar__collapse" type="button" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "展开侧栏" : "收起侧栏"}>
        {collapsed ? <SidebarExpandIcon size={16} /> : <SidebarCollapseIcon size={16} />}
        {!collapsed && <span>收起侧栏</span>}
      </button>
    </aside>
  );
}
