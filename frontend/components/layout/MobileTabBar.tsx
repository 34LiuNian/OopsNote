"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  PlusIcon,
  RepoIcon,
  ChecklistIcon,
  ScanIcon,
  BookIcon,
} from "@/components/ui/icons";

interface TabItem {
  href: string;
  label: string;
  icon: React.ElementType;
  matchExact?: boolean;
}

const TABS: TabItem[] = [
  { href: "/library", label: "题库", icon: RepoIcon },
  { href: "/batch-segment", label: "批量", icon: ScanIcon },
  { href: "/papers", label: "组卷", icon: ChecklistIcon },
  { href: "/", label: "新建", icon: PlusIcon, matchExact: true },
  { href: "/paper-builder", label: "重练", icon: BookIcon },
];

export function MobileTabBar() {
  const pathname = usePathname();

  const isActive = (tab: TabItem) => {
    if (tab.matchExact) return pathname === tab.href;
    return pathname.startsWith(tab.href);
  };

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

    </nav>
  );
}
