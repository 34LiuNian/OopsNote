"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Flash,
  FormControl,
  Heading,
  Select,
  Text,
  TextInput,
} from "@primer/react";
import { PersonIcon } from "@primer/octicons-react";
import { listUsers, resetUserPassword, updateUser } from "../../features/auth/api";
import type { UserPublic } from "../../types/api";

export default function UsersPage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<UserPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [resetPasswordMap, setResetPasswordMap] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listUsers(query);
      setItems(result.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载用户列表失败");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggleActive = async (item: UserPublic) => {
    setError("");
    setSuccess("");
    try {
      await updateUser(item.username, { is_active: !item.is_active });
      setSuccess("账号状态已更新");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新账号状态失败");
    }
  };

  const handleRoleChange = async (item: UserPublic, nextRole: "admin" | "member") => {
    if (item.role === nextRole) return;
    setError("");
    setSuccess("");
    try {
      await updateUser(item.username, { role: nextRole });
      setSuccess("角色已更新");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新角色失败");
    }
  };

  const handleResetPassword = async (item: UserPublic) => {
    const nextPassword = (resetPasswordMap[item.username] || "").trim();
    if (!nextPassword) {
      setError("请输入新密码");
      return;
    }
    setError("");
    setSuccess("");
    try {
      await resetUserPassword(item.username, { new_password: nextPassword });
      setSuccess(`已重置 ${item.username} 的密码`);
      setResetPasswordMap((prev) => ({ ...prev, [item.username]: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置密码失败");
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <PersonIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Users</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            账号管理
          </Heading>
        </Box>
      </Box>

      <Box sx={{ display: "flex", gap: 2, alignItems: "center", maxWidth: 520 }}>
        <TextInput
          block
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索用户名或昵称"
        />
        <Button onClick={() => void load()}>搜索</Button>
      </Box>

      {error ? <Flash variant="danger">{error}</Flash> : null}
      {success ? <Flash variant="success">{success}</Flash> : null}

      {loading ? (
        <Text sx={{ color: "fg.muted" }}>加载中...</Text>
      ) : (
        <Box sx={{ display: "grid", gap: 3 }}>
          {items.map((item) => (
            <Box key={item.username} className="oops-card" sx={{ p: 3, display: "grid", gap: 3 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>
                <Box>
                  <Text sx={{ fontWeight: 600 }}>{item.username}</Text>
                  <Text sx={{ color: "fg.muted", ml: 2 }}>{item.nickname || "-"}</Text>
                </Box>
                <Text className={item.is_active ? "oops-badge oops-badge-success" : "oops-badge oops-badge-danger"}>
                  {item.is_active ? "启用" : "禁用"}
                </Text>
              </Box>

              <Box sx={{ display: "flex", gap: 3, alignItems: "center", flexWrap: "wrap" }}>
                <FormControl>
                  <FormControl.Label>角色</FormControl.Label>
                  <Select
                    value={item.role}
                    onChange={(e) => void handleRoleChange(item, e.target.value as "admin" | "member")}
                  >
                    <Select.Option value="member">member</Select.Option>
                    <Select.Option value="admin">admin</Select.Option>
                  </Select>
                </FormControl>

                <Button onClick={() => void handleToggleActive(item)}>
                  {item.is_active ? "禁用账号" : "启用账号"}
                </Button>
              </Box>

              <Box sx={{ display: "flex", gap: 2, alignItems: "end", flexWrap: "wrap" }}>
                <FormControl>
                  <FormControl.Label>重置密码</FormControl.Label>
                  <TextInput
                    type="password"
                    value={resetPasswordMap[item.username] || ""}
                    onChange={(e) =>
                      setResetPasswordMap((prev) => ({
                        ...prev,
                        [item.username]: e.target.value,
                      }))
                    }
                    placeholder="输入新密码"
                  />
                </FormControl>
                <Button variant="primary" onClick={() => void handleResetPassword(item)}>
                  重置
                </Button>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
