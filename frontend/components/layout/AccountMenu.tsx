"use client";

import { Avatar, Menu } from "@mantine/core";
import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "@/components/providers";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "U";
}

export function AccountMenu() {
  const { user, signOut } = useAuth();
  const displayName = user?.displayName ?? "已登录";

  return (
    <Menu position="bottom-end" offset={8} shadow="md" width={224} withinPortal>
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
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<LogOut size={15} />} onClick={signOut}>
          退出登录
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
