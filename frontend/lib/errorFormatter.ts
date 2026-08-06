/**
 * API 错误格式化器
 * 将后端错误转换为用户友好的提示信息
 */

import { ApiError } from "./api";

/**
 * 格式化 API 错误为友好的用户提示
 * @param error - 错误对象或未知类型
 * @param fallback - 默认错误信息
 * @returns 格式化后的错误信息
 */
export function formatApiError(error: unknown, fallback = "操作失败，请稍后重试"): string {
  if (error instanceof ApiError && error.payload) {
    return error.payload.message;
  }

  if (error instanceof Error) {
    const message = error.message;
    if (message) return message;
  }

  return fallback;
}

/**
 * 获取错误的详细技术信息（用于调试）
 */
export function getErrorDetails(error: unknown): string {
  if (error instanceof ApiError && error.payload) {
    return JSON.stringify(
      { status: error.status, ...error.payload },
      null,
      2,
    );
  }
  if (error instanceof Error) {
    return `${error.name}: ${error.message}\n${error.stack || ""}`;
  }
  if (typeof error === "string") {
    return error;
  }
  return JSON.stringify(error, null, 2);
}
