import { QueryClient } from '@tanstack/react-query';

/**
 * React Query 客户端配置
 * 提供全局的查询缓存、重试策略、超时等设置
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 不自动重试，由组件自己处理错误
      retry: false,
      // 请求超时时间（5 分钟）
      gcTime: 5 * 60 * 1000,
      // 窗口聚焦时不自动重新获取
      refetchOnWindowFocus: false,
      // 网络重连时不自动重新获取
      refetchOnReconnect: false,
      // 默认不 stale，手动控制
      staleTime: Infinity,
    },
    mutations: {
      // 突变失败时不重试
      retry: false,
    },
  },
});

/**
 * 获取查询键的工厂函数
 * 用于统一管理查询键，避免硬编码
 */
export const queryKeys = {
  // 任务相关
  tasks: {
    all: ['tasks'] as const,
    lists: () => [...queryKeys.tasks.all, 'list'] as const,
    list: (filters?: { status?: string }) => [...queryKeys.tasks.lists(), filters] as const,
    details: () => [...queryKeys.tasks.all, 'detail'] as const,
    detail: (taskId: string) => [...queryKeys.tasks.details(), taskId] as const,
    stream: (taskId: string) => [...queryKeys.tasks.detail(taskId), 'stream'] as const,
  },
  
  // 标签相关
  tags: {
    all: ['tags'] as const,
    lists: () => [...queryKeys.tags.all, 'list'] as const,
    list: (dimension?: string, query?: string) => [...queryKeys.tags.lists(), { dimension, query }] as const,
    dimensions: () => [...queryKeys.tags.all, 'dimensions'] as const,
  },
  
  // 设置相关
  settings: {
    all: ['settings'] as const,
    agentModels: () => [...queryKeys.settings.all, 'agentModels'] as const,
    agentEnabled: () => [...queryKeys.settings.all, 'agentEnabled'] as const,
    agentThinking: () => [...queryKeys.settings.all, 'agentThinking'] as const,
    agentTemperature: () => [...queryKeys.settings.all, 'agentTemperature'] as const,
    models: () => [...queryKeys.settings.all, 'models'] as const,
    gateway: () => [...queryKeys.settings.all, 'gateway'] as const,
    debug: () => [...queryKeys.settings.all, 'debug'] as const,
    systemInfo: () => [...queryKeys.settings.all, 'systemInfo'] as const,
  },
};
