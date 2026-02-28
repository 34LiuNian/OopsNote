"use client";

import { useEffect, useRef, useCallback } from "react";

/**
 * 统一的定时器管理 Hook
 * 自动清理定时器，防止内存泄漏
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { start, stop, restart } = useInterval();
 *   
 *   // 启动定时器
 *   start(() => {
 *     console.log("tick");
 *   }, 1000);
 *   
 *   // 组件卸载时自动清理
 * }
 * ```
 */
export function useInterval() {
  const intervalIdRef = useRef<number | null>(null);
  const callbackRef = useRef<(() => void) | null>(null);

  /**
   * 停止当前定时器
   */
  const stop = useCallback(() => {
    if (intervalIdRef.current !== null) {
      window.clearInterval(intervalIdRef.current);
      intervalIdRef.current = null;
    }
    callbackRef.current = null;
  }, []);

  /**
   * 启动定时器
   * @param callback - 回调函数
   * @param delay - 延迟（毫秒）
   */
  const start = useCallback(
    (callback: () => void, delay: number) => {
      // 先停止之前的定时器
      stop();

      callbackRef.current = callback;
      intervalIdRef.current = window.setInterval(() => {
        callbackRef.current?.();
      }, delay);
    },
    [stop]
  );

  /**
   * 重启定时器（先停止再启动）
   */
  const restart = useCallback(
    (callback: () => void, delay: number) => {
      stop();
      start(callback, delay);
    },
    [stop, start]
  );

  /**
   * 立即执行一次回调，然后启动定时器
   */
  const startWithImmediate = useCallback(
    (callback: () => void, delay: number) => {
      callback();
      start(callback, delay);
    },
    [start]
  );

  // 组件卸载时自动清理
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    /** 启动定时器 */
    start,
    /** 停止定时器 */
    stop,
    /** 重启定时器 */
    restart,
    /** 立即执行并启动 */
    startWithImmediate,
    /** 定时器是否正在运行 */
    isRunning: intervalIdRef.current !== null,
  };
}

/**
 * 简化的定时器 Hook（固定回调和延迟）
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   // 每 1 秒执行一次
 *   useIntervalFixed(() => {
 *     console.log("tick");
 *   }, 1000);
 * }
 * ```
 */
export function useIntervalFixed(callback: () => void, delay: number | null) {
  const savedCallback = useRef(callback);

  // 记住最新的回调
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delay === null) {
      return;
    }

    function tick() {
      savedCallback.current();
    }

    const id = window.setInterval(tick, delay);
    return () => window.clearInterval(id);
  }, [delay]);
}
