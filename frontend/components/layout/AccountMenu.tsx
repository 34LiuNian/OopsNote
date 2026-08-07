"use client";

import { Avatar, Menu } from "@mantine/core";
import { Gauge, LogOut, UserRound } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/components/providers";

type QuotaSummary = {
  daily_success_limit: number;
  used_units: number;
};

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "U";
}

export function AccountMenu() {
  const { user, signOut } = useAuth();
  const displayName = user?.displayName ?? "登录";
  const [quota, setQuota] = useState<QuotaSummary | null>(null);

  async function loadQuota() {
    try {
      const response = await fetch("/api/backend/me/quota", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json() as { quota?: QuotaSummary };
      setQuota(payload.quota || null);
    } catch {
      // Keep the account menu usable when the optional quota projection is unavailable.
    }
  }

  return (
    <Menu position="bottom-end" offset={8} shadow="md" width={224} withinPortal onOpen={() => void loadQuota()}>
      <Menu.Target>
        <button type="button" className="oops-account-trigger" aria-label="账户菜单">
          <Avatar src={user?.picture} alt="" size={28} radius="xl" color="gray">
            {user ? initials(displayName) : <UserRound size={16} />}
          </Avatar>
          <span className="oops-account-trigger__name">{displayName}</span>
        </button>
      </Menu.Target>
      <Menu.Dropdown>
        <div className="oops-account-menu__identity">
          <strong>{displayName}</strong>
          {user?.email && <span>{user.email}</span>}
        </div>
        {quota && (
          <div className="oops-account-menu__quota">
            <Gauge size={15} />
            <span>今日剩余</span>
            <strong>{Math.max(0, quota.daily_success_limit - quota.used_units)} / {quota.daily_success_limit}</strong>
          </div>
        )}
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<LogOut size={15} />} onClick={signOut}>
          退出登录
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
