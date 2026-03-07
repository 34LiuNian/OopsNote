"use client";

import { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  PlusIcon,
  RepoIcon,
  ChecklistIcon,
  GearIcon,
  KebabHorizontalIcon,
  TagIcon,
  PersonIcon,
  BookIcon,
} from "@primer/octicons-react";
import { getCurrentUser, onAuthChanged } from "../../features/auth/store";

interface TabItem {
  href: string;
  label: string;
  icon: React.ElementType;
  matchExact?: boolean;
}

const TABS: TabItem[] = [
  { href: "/", label: "新建", icon: PlusIcon, matchExact: true },
  { href: "/library", label: "题库", icon: RepoIcon },
  { href: "/paper-builder", label: "组卷", icon: ChecklistIcon },
  { href: "/settings", label: "设置", icon: GearIcon },
];

const MORE_ITEMS: TabItem[] = [
  { href: "/account", label: "账号设置", icon: PersonIcon },
  { href: "/users", label: "账号管理", icon: PersonIcon },
  { href: "/tags", label: "标签管理", icon: TagIcon },
  { href: "/debug", label: "Debug", icon: BookIcon },
];

export function MobileTabBar() {
  const pathname = usePathname();
  const [showMore, setShowMore] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const syncRole = () => setIsAdmin(getCurrentUser()?.role === "admin");
    syncRole();
    return onAuthChanged(syncRole);
  }, []);

  // Close "more" menu on click outside
  useEffect(() => {
    if (!showMore) return;
    const handler = (e: PointerEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setShowMore(false);
      }
    };
    document.addEventListener("pointerdown", handler);
    return () => document.removeEventListener("pointerdown", handler);
  }, [showMore]);

  // Close when navigating
  useEffect(() => setShowMore(false), [pathname]);

  const isActive = (tab: TabItem) => {
    if (tab.matchExact) return pathname === tab.href;
    return pathname.startsWith(tab.href);
  };

  const isMoreActive = MORE_ITEMS.some((item) => pathname.startsWith(item.href));

  const visibleMore = MORE_ITEMS.filter(
    (item) => isAdmin || !(["/users", "/tags", "/debug"].includes(item.href))
  );

  return (
    <nav className="oops-mobile-tabbar">
      {TABS.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={isActive(tab) ? "active" : ""}
        >
          <tab.icon size={20} />
          <span>{tab.label}</span>
        </Link>
      ))}

      {/* More button */}
      <div ref={moreRef} style={{ flex: 1, position: "relative" }}>
        <button
          className={isMoreActive ? "active" : ""}
          onClick={() => setShowMore((v) => !v)}
          style={{ width: "100%", height: "100%" }}
        >
          <KebabHorizontalIcon size={20} />
          <span>更多</span>
        </button>

        {showMore && (
          <div
            style={{
              position: "absolute",
              bottom: "100%",
              right: 0,
              marginBottom: 8,
              minWidth: 90,
              borderRadius: "var(--oops-radius-md)",
              border: "1px solid var(--borderColor-default)",
              background: "var(--bgColor-default)",
              boxShadow: "var(--oops-shadow-float)",
              overflow: "hidden",
              animation: "slideUp 0.15s ease-out",
              zIndex: 50,
            }}
          >
            {visibleMore.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 12px",
                  fontSize: 13,
                  color: pathname.startsWith(item.href)
                    ? "var(--fgColor-accent)"
                    : "var(--fgColor-default)",
                  textDecoration: "none",
                  borderBottom: "1px solid var(--borderColor-muted)",
                  backgroundColor: "transparent",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = "var(--bgColor-muted)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = "transparent";
                }}
              >
                <item.icon size={14} />
                {item.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}
