"use client";

import { Menu } from "@mantine/core";
import { Gauge, LogOut, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/providers";
import { InitialAvatar } from "@/components/ui/InitialAvatar";

type QuotaSummary = {
  daily_success_limit: number;
  used_units: number;
};

export function AccountMenu() {
  const { user, signOut } = useAuth();
  const router = useRouter();
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
          {user ? <InitialAvatar name={displayName} image={user.picture} size={28} /> : <UserRound size={16} />}
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
        <Menu.Item leftSection={<UserRound size={15} />} onClick={() => router.push("/settings/account")}>
          个人账号
        </Menu.Item>
        <Menu.Item color="red" leftSection={<LogOut size={15} />} onClick={signOut}>
          退出登录
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
