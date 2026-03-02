"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Box,
  Button,
  Flash,
  FormControl,
  Heading,
  Spinner,
  Text,
  TextInput,
} from "@primer/react";
import {
  CheckCircleIcon,
  LightBulbIcon,
  LockIcon,
  RepoIcon,
  PersonIcon,
  RocketIcon,
} from "@primer/octicons-react";

import { getRegistrationEnabled, login, register } from "../../features/auth/api";
import { saveAuthSession } from "../../features/auth/store";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [nickname, setNickname] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getRegistrationEnabled()
      .then((result) => {
        if (cancelled) return;
        setRegistrationEnabled(Boolean(result.enabled));
      })
      .catch(() => {
        if (cancelled) return;
        setRegistrationEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!registrationEnabled && isRegisterMode) {
      setIsRegisterMode(false);
    }
  }, [registrationEnabled, isRegisterMode]);

  const next = useMemo(() => {
    const candidate = searchParams.get("next") || "/";
    return candidate.startsWith("/") ? candidate : "/";
  }, [searchParams]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    if (isRegisterMode) {
      if (!passwordConfirm) {
        setError("请确认密码");
        return;
      }
      if (password !== passwordConfirm) {
        setError("两次密码输入不一致");
        return;
      }
    }

    setSubmitting(true);
    setError("");
    try {
      const normalizedUsername = username.trim();
      const result = isRegisterMode
        ? await register({
            username: normalizedUsername,
            password,
            nickname: nickname.trim() || undefined,
            avatar_url: avatarUrl.trim() || undefined,
          })
        : await login({ username: normalizedUsername, password });
      saveAuthSession({
        accessToken: result.access_token,
        expiresIn: result.expires_in,
        user: result.user,
      });
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : isRegisterMode ? "注册失败，请稍后重试" : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        bg: "canvas.default",
      }}
    >
      {/* ===== 左侧品牌区 ===== */}
      <Box
        className="oops-login-brand"
        sx={{
          display: ["none", "none", "flex"],
          flex: "0 0 440px",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          p: 6,
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* 呼吸光晕 */}
        <Box
          className="oops-login-glow"
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            width: 360,
            height: 360,
            marginTop: -180,
            marginLeft: -180,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(255,255,255,0.12) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        {/* Logo */}
        <Box
          className="oops-login-logo"
          sx={{
            width: 80,
            height: 80,
            borderRadius: "20px",
            // bg: "rgba(255,255,255,0.15)",
            backdropFilter: "blur(10px)",
            // border: "1.5px solid rgba(255,255,255,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            // boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
          }}
        >
           <RepoIcon size={80} />
        </Box>
        <Heading
          as="h1"
          sx={{
            color: "white",
            fontSize: "64px",
            fontWeight: "bold",
            letterSpacing: "-0.02em",
            textAlign: "center",
            fontFamily: "'OopsNoteFont', 'Inter', 'HarmonyOS Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          }}
        >
          OopsNote
        </Heading>
        <Text
          sx={{
            color: "rgba(255,255,255,0.7)",
            fontSize: 2,
            textAlign: "center",
            maxWidth: 280,
            lineHeight: 1.7,
          }}
        >
          智能题目解析、错题沉淀、知识点打标
        </Text>

        {/* 功能亮点 */}
        <Box
          sx={{
            mt: 4,
            display: "flex",
            flexDirection: "column",
            gap: 3,
            width: "100%",
            maxWidth: 260,
          }}
        >
          {[
            { icon: RocketIcon, text: "AI 一键解题与解析" },
            { icon: CheckCircleIcon, text: "多维标签自动打标" },
            { icon: LightBulbIcon, text: "错因分析与知识图谱" },
          ].map(({ icon: Icon, text }) => (
            <Box
              key={text}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 3,
                px: 3,
                py: "10px",
                borderRadius: "var(--oops-radius-md)",
                bg: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <Icon size={16} />
              <Text sx={{ color: "rgba(255,255,255,0.85)", fontSize: 1 }}>{text}</Text>
            </Box>
          ))}
        </Box>

        {/* 装饰浮动圆 */}
        <Box className="oops-login-circle oops-login-circle-1" />
        <Box className="oops-login-circle oops-login-circle-2" />
        <Box className="oops-login-circle oops-login-circle-3" />
      </Box>

      {/* ===== 右侧表单区 ===== */}
      <Box
        className="oops-login-right"
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          px: [4, 5, 6],
          py: 6,
          position: "relative",
        }}
      >
        {/* 小屏显示 logo 文字 */}
        <Box
          sx={{
            display: ["flex", "flex", "none"],
            alignItems: "center",
            gap: 2,
            mb: 5,
            color: "accent.fg",
          }}
        >
          <RepoIcon size={24} />
          <Text sx={{ fontSize: 4, fontWeight: "bold", fontFamily: "'OopsNoteFont', 'Inter', 'HarmonyOS Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>OopsNote</Text>
        </Box>

        <Box
          as="form"
          onSubmit={handleSubmit}
          className="oops-login-card"
          sx={{
            width: "100%",
            maxWidth: 400,
            border: "1px solid",
            borderColor: "border.default",
            borderRadius: "var(--oops-radius-lg)",
            p: 5,
            bg: "canvas.overlay",
            boxShadow: "var(--oops-shadow-float)",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <Box>
            <Heading as="h2" sx={{ fontSize: 4, mb: 1, fontWeight: "bold" }}>
              {isRegisterMode ? "创建账号" : "欢迎回来"}
            </Heading>
            <Text sx={{ color: "fg.muted", fontSize: 1 }}>
              {isRegisterMode ? "填写信息后立即创建并登录" : "登录您的帐号以继续使用"}
            </Text>
          </Box>

          <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <FormControl>
              <FormControl.Label>用户名</FormControl.Label>
              <TextInput
                leadingVisual={PersonIcon}
                block
                size="large"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                placeholder="请输入用户名"
              />
            </FormControl>

            {isRegisterMode ? (
              <>
                <FormControl>
                  <FormControl.Label>昵称（可选）</FormControl.Label>
                  <TextInput
                    block
                    size="large"
                    value={nickname}
                    onChange={(e) => setNickname(e.target.value)}
                    placeholder="请输入昵称"
                  />
                </FormControl>

                <FormControl>
                  <FormControl.Label>头像地址（可选）</FormControl.Label>
                  <TextInput
                    block
                    size="large"
                    value={avatarUrl}
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    placeholder="https://..."
                  />
                </FormControl>
              </>
            ) : null}

            <FormControl>
              <FormControl.Label>密码</FormControl.Label>
              <TextInput
                leadingVisual={LockIcon}
                block
                size="large"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={isRegisterMode ? "new-password" : "current-password"}
                placeholder="请输入密码"
              />
            </FormControl>

            {isRegisterMode ? (
              <FormControl>
                <FormControl.Label>确认密码</FormControl.Label>
                <TextInput
                  leadingVisual={LockIcon}
                  block
                  size="large"
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  autoComplete="new-password"
                  placeholder="请再次输入密码"
                />
              </FormControl>
            ) : null}
          </Box>

          {error ? (
            <Flash variant="danger" className="oops-slide-down">
              {error}
            </Flash>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            size="large"
            block
            disabled={submitting}
            sx={{
              gap: 2,
              height: 44,
              fontSize: 2,
              fontWeight: 600,
              borderRadius: "var(--oops-radius-md)",
              boxShadow: submitting ? "none" : "0 2px 8px rgba(9,105,218,0.35)",
              transition: "box-shadow var(--oops-transition-fast), transform var(--oops-transition-fast)",
              "&:hover:not(:disabled)": {
                boxShadow: "0 4px 16px rgba(9,105,218,0.4)",
                transform: "translateY(-1px)",
              },
              "&:active:not(:disabled)": {
                transform: "translateY(0)",
              },
            }}
          >
            {submitting ? (
              <>
                <Spinner size="small" />
                {isRegisterMode ? "注册中…" : "登录中…"}
              </>
            ) : (
              isRegisterMode ? "注册并登录" : "登录"
            )}
          </Button>

          {registrationEnabled ? (
            <Button
              type="button"
              variant="invisible"
              size="small"
              onClick={() => {
                setError("");
                setIsRegisterMode((prev) => !prev);
              }}
            >
              {isRegisterMode ? "已有账号？去登录" : "没有账号？去注册"}
            </Button>
          ) : null}
        </Box>

        {/* 底部版权 */}
        {/* <Text
          sx={{
            position: "absolute",
            bottom: 4,
            color: "fg.subtle",
            fontSize: 0,
          }}
        >
          © {new Date().getFullYear()} OopsNote
        </Text> */}
      </Box>
    </Box>
  );
}
