"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck, Users } from "lucide-react";
import {
  BlocksIcon,
  BookIcon,
  ChecklistIcon,
  GearIcon,
  GitBranchIcon,
  PlusIcon,
  RepoIcon,
  ScanIcon,
} from "@/components/ui/icons";
import { useAuth } from "@/components/providers/AuthProvider";
import { isAdminUser } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/library", label: "题库", icon: RepoIcon, section: "main" },
  { href: "/batch-segment", label: "批量扫描", icon: ScanIcon, section: "main" },
  { href: "/papers", label: "组卷", icon: ChecklistIcon, section: "main" },
  { href: "/new", label: "新建题目", icon: PlusIcon, section: "main", matchExact: true },
  { href: "/paper-builder", label: "快速重练", icon: BookIcon, section: "main" },
  { href: "/settings/members", label: "成员", icon: Users, section: "admin" },
  { href: "/settings/access", label: "注册与访问", icon: ShieldCheck, section: "admin" },
  { href: "/settings/channels", label: "AI 渠道", icon: BlocksIcon, section: "admin" },
  { href: "/settings/policy", label: "AI 策略", icon: GitBranchIcon, section: "admin" },
  { href: "/settings", label: "系统运行", icon: GearIcon, section: "admin", matchExact: true },
  { href: "/debug", label: "渲染调试", icon: BookIcon, section: "admin" },
] as const;

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
  const mainItems = NAV_ITEMS.filter((item) => item.section === "main");
  const adminItems = NAV_ITEMS.filter((item) => item.section === "admin" && isAdminUser(user));
  const isActive = (item: (typeof NAV_ITEMS)[number]) => "matchExact" in item && item.matchExact ? pathname === item.href : pathname.startsWith(item.href);

  const renderItem = (item: (typeof NAV_ITEMS)[number]) => {
    const active = isActive(item);
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
  };

  return (
    <nav className="app-sidebar__nav" aria-label={ariaLabel}>
      {mainItems.map(renderItem)}
      {adminItems.length > 0 && (
        <>
          <div className="app-sidebar__divider" />
          {!collapsed && <span className="app-sidebar__label">系统管理</span>}
          {adminItems.map(renderItem)}
        </>
      )}
    </nav>
  );
}

export function Sidebar({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: (href: string) => void }) {
  return (
    <aside id="oops-primary-sidebar" className={`app-sidebar oops-desktop-sidebar${collapsed ? " is-collapsed" : ""}`}>
      <NavigationItems collapsed={collapsed} onNavigate={onNavigate} ariaLabel={collapsed ? "快捷导航" : "主导航"} />
    </aside>
  );
}
