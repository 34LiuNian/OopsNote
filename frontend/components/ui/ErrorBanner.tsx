"use client";

type ErrorBannerProps = {
  message: string;
  title?: string;
};

export function ErrorBanner({ message, title = "操作失败" }: ErrorBannerProps) {
  if (!message) return null;
  return (
    <div className="oops-error-banner" role="alert">
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}
