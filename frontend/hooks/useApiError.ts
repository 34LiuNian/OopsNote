"use client";

import { useCallback, useState } from "react";
import { notify } from "@/lib/notify";
import { formatApiError, getErrorDetails } from "../lib/errorFormatter";

/**
 * 统一的 API 错误处理 Hook
 * 提供错误状态管理、错误提示和错误恢复功能
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { error, handleError, clearError, isLoading } = useApiError();
 *   
 *   const handleAction = async () => {
 *     try {
 *       await someApiCall();
 *     } catch (err) {
 *       handleError(err, "操作失败");
 *     }
 *   };
 * }
 * ```
 */
export function useApiError(options?: {
  /** 是否自动显示 toast 提示 */
  autoShowToast?: boolean;
  /** 默认错误信息 */
  defaultFallback?: string;
  /** 错误发生时的回调 */
  onError?: (error: string, details?: string) => void;
}) {
  const {
    autoShowToast = true,
    defaultFallback = "操作失败，请稍后重试",
    onError,
  } = options ?? {};

  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  /**
   * 处理错误
   * @param error - 错误对象
   * @param fallback - 默认错误信息
   * @param showDetails - 是否显示详细信息（开发环境）
   */
  const handleError = useCallback(
    (
      error: unknown,
      fallback?: string,
      options?: {
        showDetails?: boolean;
        title?: string;
      }
    ) => {
      const formattedError = formatApiError(error, fallback ?? defaultFallback);
      const details = getErrorDetails(error);
      
      setError(formattedError);
      setErrorDetails(options?.showDetails ? details : null);
      setIsLoading(false);

      // 自动显示 toast
      if (autoShowToast) {
        notify.error({
          title: options?.title ?? "操作失败",
          description: formattedError,
        });
      }

      // 调用错误回调
      onError?.(formattedError, details);

      // 开发环境打印详细错误
      if (process.env.NODE_ENV === "development") {
        console.error("[API Error]", formattedError, details);
      }
    },
    [autoShowToast, defaultFallback, onError]
  );

  /**
   * 清除错误状态
   */
  const clearError = useCallback(() => {
    setError(null);
    setErrorDetails(null);
  }, []);

  /**
   * 包装异步操作，自动处理错误
   * @param operation - 异步操作函数
   * @param fallback - 默认错误信息
   */
  const withErrorHandling = useCallback(
    async <T,>(
      operation: () => Promise<T>,
      fallback?: string
    ): Promise<T | null> => {
      setIsLoading(true);
      try {
        const result = await operation();
        setIsLoading(false);
        return result;
      } catch (err) {
        handleError(err, fallback);
        return null;
      }
    },
    [handleError]
  );

  return {
    /** 当前错误信息 */
    error,
    /** 错误详细信息（开发环境） */
    errorDetails,
    /** 是否正在加载 */
    isLoading,
    /** 设置加载状态 */
    setIsLoading,
    /** 处理错误 */
    handleError,
    /** 清除错误 */
    clearError,
    /** 包装异步操作 */
    withErrorHandling,
  };
}

/**
 * 简化的错误处理 Hook（仅需要基本功能时使用）
 */
export function useSimpleError() {
  const [error, setError] = useState<string | null>(null);

  const handleError = useCallback((err: unknown, fallback: string) => {
    const message = formatApiError(err, fallback);
    setError(message);
    notify.error({ title: fallback, description: message });
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { error, handleError, clearError };
}
