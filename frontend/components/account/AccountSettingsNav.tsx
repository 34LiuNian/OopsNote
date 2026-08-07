"use client";

import { Gauge, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./AccountSettingsNav.module.css";

const items = [
  { href: "/settings/account", label: "个人资料", icon: UserRound },
  { href: "/settings/account/security", label: "账号安全", icon: ShieldCheck },
  { href: "/settings/account/usage", label: "用量与额度", icon: Gauge },
];

export function AccountSettingsNav() {
  const pathname = usePathname();
  return (
    <nav className={styles.nav} aria-label="个人账号">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <Link key={item.href} href={item.href} className={`${styles.link}${active ? ` ${styles.active}` : ""}`} aria-current={active ? "page" : undefined}>
            <item.icon size={16} aria-hidden="true" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
