"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Box, Button, FormControl, Heading, Text, TextInput } from "@primer/react";

import { login } from "../../features/auth/api";
import { saveAuthSession } from "../../features/auth/store";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

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

    setSubmitting(true);
    setError("");
    try {
      const result = await login({ username: username.trim(), password });
      saveAuthSession({
        accessToken: result.access_token,
        expiresIn: result.expires_in,
        user: result.user,
      });
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 3,
      }}
    >
      <Box
        as="form"
        onSubmit={handleSubmit}
        sx={{
          width: "100%",
          maxWidth: 360,
          border: "1px solid",
          borderColor: "border.default",
          borderRadius: 2,
          p: 4,
          bg: "canvas.default",
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        <Box>
          <Heading as="h2" sx={{ mb: 1 }}>
            登录 OopsNote
          </Heading>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>请输入账号后继续使用。</Text>
        </Box>

        <FormControl>
          <FormControl.Label>用户名</FormControl.Label>
          <TextInput
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </FormControl>

        <FormControl>
          <FormControl.Label>密码</FormControl.Label>
          <TextInput
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </FormControl>

        {error ? (
          <Text sx={{ color: "danger.fg", fontSize: 1 }}>
            {error}
          </Text>
        ) : null}

        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "登录中..." : "登录"}
        </Button>
      </Box>
    </Box>
  );
}
