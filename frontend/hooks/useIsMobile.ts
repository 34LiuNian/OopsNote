"use client";

import { useEffect, useState } from "react";

/** Primer 第一断点 544px */
const MOBILE_BREAKPOINT = "(max-width: 543px)";
const TABLET_BREAKPOINT = "(max-width: 1011px)";

function subscribe(query: string, cb: (matches: boolean) => void) {
  const mql = window.matchMedia(query);
  const handler = (e: MediaQueryListEvent) => cb(e.matches);
  mql.addEventListener("change", handler);
  cb(mql.matches);
  return () => mql.removeEventListener("change", handler);
}

/**
 * 判断当前视口是否为移动端（< 544px）。
 * SSR 期间默认 false，客户端首帧后立即同步。
 */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(false);
  useEffect(() => subscribe(MOBILE_BREAKPOINT, setMobile), []);
  return mobile;
}

/**
 * 判断当前视口是否 ≤ 平板宽度（< 1012px）。
 */
export function useIsCompact(): boolean {
  const [compact, setCompact] = useState(false);
  useEffect(() => subscribe(TABLET_BREAKPOINT, setCompact), []);
  return compact;
}
