"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Button, Flash, FormControl, Heading, Text, TextInput } from "@primer/react";
import { PersonIcon } from "@primer/octicons-react";
import { getAccountMe, updateAccountMe, updatePassword } from "../../features/auth/api";
import { clearAuthSession, getCurrentUser, updateSessionUser } from "../../features/auth/store";

export default function AccountPage() {
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [username, setUsername] = useState("");
  const [nickname, setNickname] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  useEffect(() => {
    let cancelled = false;
    void getAccountMe()
      .then((result) => {
        if (cancelled) return;
        setUsername(result.user.username || "");
        setNickname(result.user.nickname || "");
        setAvatarUrl(result.user.avatar_url || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "加载账号信息失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const originalUsername = useMemo(() => getCurrentUser()?.username || "", []);

  const handleSaveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSavingProfile(true);
    try {
      const result = await updateAccountMe({
        username: username.trim(),
        nickname: nickname.trim(),
        avatar_url: avatarUrl.trim(),
      });
      updateSessionUser(result.user);
      setSuccess("账号资料保存成功");
      if (originalUsername && result.user.username !== originalUsername) {
        clearAuthSession();
        window.location.assign("/login");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存账号资料失败");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!currentPassword || !newPassword) {
      setError("请输入当前密码和新密码");
      return;
    }
    setError("");
    setSuccess("");
    setSavingPassword(true);
    try {
      const result = await updatePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setSuccess(result.message || "密码修改成功");
    } catch (err) {
      setError(err instanceof Error ? err.message : "修改密码失败");
    } finally {
      setSavingPassword(false);
    }
  };

  if (loading) {
    return <Text sx={{ color: "fg.muted" }}>加载中...</Text>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 720 }}>
      <Box className="oops-section-header" sx={{ border: "none !important", mb: 0, pb: 2 }}>
        <PersonIcon size={20} />
        <Box sx={{ flex: 1 }}>
          <Text className="oops-section-subtitle">Account</Text>
          <Heading as="h2" className="oops-section-title" sx={{ m: 0 }}>
            账号设置
          </Heading>
        </Box>
      </Box>

      {error ? <Flash variant="danger">{error}</Flash> : null}
      {success ? <Flash variant="success">{success}</Flash> : null}

      <Box as="form" onSubmit={handleSaveProfile} className="oops-card" sx={{ p: 4, display: "grid", gap: 3 }}>
        <Heading as="h3" sx={{ fontSize: 2, m: 0 }}>
          个人资料
        </Heading>

        <FormControl>
          <FormControl.Label>用户名</FormControl.Label>
          <TextInput block value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" />
        </FormControl>

        <FormControl>
          <FormControl.Label>昵称</FormControl.Label>
          <TextInput block value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder="昵称" />
        </FormControl>

        <FormControl>
          <FormControl.Label>头像地址</FormControl.Label>
          <TextInput block value={avatarUrl} onChange={(e) => setAvatarUrl(e.target.value)} placeholder="https://..." />
        </FormControl>

        <Box>
          <Button type="submit" variant="primary" disabled={savingProfile}>
            {savingProfile ? "保存中..." : "保存资料"}
          </Button>
        </Box>
      </Box>

      <Box as="form" onSubmit={handleChangePassword} className="oops-card" sx={{ p: 4, display: "grid", gap: 3 }}>
        <Heading as="h3" sx={{ fontSize: 2, m: 0 }}>
          修改密码
        </Heading>

        <FormControl>
          <FormControl.Label>当前密码</FormControl.Label>
          <TextInput
            block
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
          />
        </FormControl>

        <FormControl>
          <FormControl.Label>新密码</FormControl.Label>
          <TextInput
            block
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
        </FormControl>

        <Box>
          <Button type="submit" variant="primary" disabled={savingPassword}>
            {savingPassword ? "提交中..." : "修改密码"}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
