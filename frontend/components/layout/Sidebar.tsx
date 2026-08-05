"use client";

import { usePathname } from "next/navigation";
import {
  PlusIcon,
  RepoIcon,
  BookIcon,
  ChecklistIcon,
  ScanIcon,
  GearIcon,
  CpuIcon,
  GitBranchIcon,
} from "@/components/ui/icons";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { isAdminUser } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/", label: "新建题目", icon: PlusIcon, section: "main" },
  { href: "/batch-segment", label: "批量扫描", icon: ScanIcon, section: "main" },
  { href: "/library", label: "题库", icon: RepoIcon, section: "main" },
  { href: "/papers", label: "组卷", icon: ChecklistIcon, section: "main" },
  { href: "/paper-builder", label: "快速重练", icon: BookIcon, section: "main" },
  { href: "/debug", label: "渲染调试", icon: BookIcon, section: "tools" },
  { href: "/settings", label: "设置", icon: GearIcon, section: "tools" },
  { href: "/settings/channels", label: "AI 渠道", icon: CpuIcon, section: "admin" },
  { href: "/settings/policy", label: "LangChain 策略", icon: GitBranchIcon, section: "admin" },
];

function NavigationItems({
  collapsed,
  onNavigate,
  ariaLabel,
}: {
  collapsed: boolean;
  onNavigate?: (href: string) => void;
  ariaLabel: string;
}) {
  const pathname = usePathname();
  const { user } = useAuth();

  const mainItems = NAV_ITEMS.filter((i) => i.section === "main");
  const toolItems = NAV_ITEMS.filter((i) => i.section === "tools");
  const adminItems = NAV_ITEMS.filter((i) => i.section === "admin" && isAdminUser(user));

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <nav className="app-sidebar__nav" aria-label={ariaLabel}>
        {mainItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`app-sidebar__link${active ? " is-active" : ""}`}
              aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              onClick={() => onNavigate?.(item.href)}
            >
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
            <Link
              key={item.href}
              href={item.href}
              className={`app-sidebar__link${active ? " is-active" : ""}`}
              aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              onClick={() => onNavigate?.(item.href)}
            >
              <item.icon size={17} strokeWidth={1.9} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
        {adminItems.length > 0 && <>
          <div className="app-sidebar__divider" />
          {!collapsed && <span className="app-sidebar__label">管理</span>}
          {adminItems.map((item) => {
            const active = isActive(item.href);
            return (
              <Link key={item.href} href={item.href} className={`app-sidebar__link${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined} onClick={() => onNavigate?.(item.href)}>
                <item.icon size={17} strokeWidth={1.9} />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </>}
    </nav>
  );
}

export function Sidebar({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: (href: string) => void;
}) {
  return (
    <aside id="oops-primary-sidebar" className={`app-sidebar oops-desktop-sidebar${collapsed ? " is-collapsed" : ""}`}>
      <NavigationItems
        collapsed={collapsed}
        onNavigate={onNavigate}
        ariaLabel={collapsed ? "快捷导航" : "主导航"}
      />
    </aside>
  );
}
