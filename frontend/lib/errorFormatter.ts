/**
 * API 错误格式化器
 * 将后端错误转换为用户友好的提示信息
 */

/**
 * 常见错误映射表
 */
const ERROR_MESSAGE_MAP: Record<string, string> = {
  // 网络错误
  "Failed to fetch": "网络连接失败，请检查网络后重试",
  "NetworkError": "网络连接失败，请检查网络后重试",
  
  // 上传相关
  "文件过大": "图片文件过大，请选择小于 10MB 的文件",
  "不支持的文件格式": "不支持的文件格式，请上传图片文件（JPG/PNG 等）",
  "无法读取文件": "文件读取失败，请重新选择文件",
  
  // 任务相关
  "任务不存在": "任务不存在或已被删除",
  "任务已取消": "任务已被取消",
  "任务处理失败": "任务处理失败，请稍后重试",
  
  // OCR 相关
  "OCR 识别失败": "题目识别失败，请尝试重新上传或手动输入",
  "JSON 解析失败": "识别结果格式错误，请稍后重试",
  
  // LaTeX 相关
  "LaTeX 编译失败": "公式渲染失败，请检查公式格式是否正确",
  "公式渲染失败": "公式渲染失败，请检查公式格式",
  
  // 通用错误
  "服务器错误": "服务器繁忙，请稍后重试",
  "权限不足": "权限不足，无法执行此操作",
  "请求超时": "请求超时，请检查网络连接后重试",
};

/**
 * 判断是否为网络错误
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof Error) {
    return (
      error.message.includes("Failed to fetch") ||
      error.message.includes("NetworkError") ||
      error.message.includes("network")
    );
  }
  return false;
}

/**
 * 格式化 API 错误为友好的用户提示
 * @param error - 错误对象或未知类型
 * @param fallback - 默认错误信息
 * @returns 格式化后的错误信息
 */
export function formatApiError(error: unknown, fallback = "操作失败，请稍后重试"): string {
  if (error instanceof Error) {
    const message = error.message;
    
    // 检查是否有关键词匹配
    for (const [key, friendlyMessage] of Object.entries(ERROR_MESSAGE_MAP)) {
      if (message.includes(key)) {
        return friendlyMessage;
      }
    }
    
    // 网络错误特殊处理
    if (isNetworkError(error)) {
      return ERROR_MESSAGE_MAP["Failed to fetch"];
    }
    
    // 返回原始错误信息（如果不太技术化）
    if (message.length < 100 && !message.includes("at ") && !message.includes("Error:")) {
      return message;
    }
  }
  
  // 未知错误类型
  return fallback;
}

/**
 * 获取错误的详细技术信息（用于调试）
 */
export function getErrorDetails(error: unknown): string {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}\n${error.stack || ""}`;
  }
  if (typeof error === "string") {
    return error;
  }
  return JSON.stringify(error, null, 2);
}
