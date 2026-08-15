const USERNAME_PATTERN = /^[A-Za-z0-9_.]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const PASSWORD_MIN_LENGTH = 12;

export function validateUsername(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "请输入用户名。";
  if (trimmed.length < 3 || trimmed.length > 32) return "用户名需为 3–32 位。";
  if (!USERNAME_PATTERN.test(trimmed)) return "只能使用字母、数字、下划线和点。";
  return null;
}

export function validateEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "请输入邮箱。";
  if (!EMAIL_PATTERN.test(trimmed)) return "请输入有效的邮箱地址。";
  return null;
}

export function validatePassword(value: string): string | null {
  if (!value) return "请输入密码。";
  if (value.length < PASSWORD_MIN_LENGTH) return `密码至少需要 ${PASSWORD_MIN_LENGTH} 个字符。`;
  return null;
}

export function validateInvitationCode(value: string, required: boolean): string | null {
  if (required && !value.trim()) return "请输入邀请码。";
  return null;
}

export function validateIdentifier(value: string): string | null {
  if (!value.trim()) return "请输入用户名或邮箱。";
  return null;
}
