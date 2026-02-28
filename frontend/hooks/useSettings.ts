"use client";

import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '../lib/api';
import { queryKeys } from '../lib/queryClient';

/**
 * 获取可用的 Agent 模型列表
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAgentModels();
 * ```
 */
export function useAgentModels() {
  return useQuery({
    queryKey: queryKeys.settings.agentModels(),
    queryFn: () => fetchJson<{ models: string[] }>('/settings/agent-models'),
    // 模型列表很少变化，缓存 1 小时
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * 获取 Agent 启用状态
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAgentEnabled();
 * ```
 */
export function useAgentEnabled() {
  return useQuery({
    queryKey: queryKeys.settings.agentEnabled(),
    queryFn: () => fetchJson<{ enabled: boolean }>('/settings/agent-enabled'),
    // 启用状态可能变化，缓存 5 分钟
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * 获取 Agent 思考模式设置
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAgentThinking();
 * ```
 */
export function useAgentThinking() {
  return useQuery({
    queryKey: queryKeys.settings.agentThinking(),
    queryFn: () => fetchJson<{ thinking: boolean }>('/settings/agent-thinking'),
    // 思考模式设置很少变化，缓存 1 小时
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * 获取所有可用模型
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useModels();
 * ```
 */
export function useModels() {
  return useQuery({
    queryKey: queryKeys.settings.models(),
    queryFn: () => fetchJson<{ models: string[] }>('/models'),
    // 模型列表很少变化，缓存 1 小时
    staleTime: 60 * 60 * 1000,
  });
}
