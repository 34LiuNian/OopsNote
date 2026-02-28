"use client";

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '../lib/api';
import type { TaskResponse, TasksResponse } from '../types/api';
import { queryKeys } from '../lib/queryClient';

/**
 * 获取单个任务详情
 * 
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTask(taskId);
 * ```
 */
export function useTask(taskId: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.detail(taskId || ''),
    queryFn: () => fetchJson<TaskResponse>(`/tasks/${taskId}`),
    enabled: !!taskId,
    // 任务数据不缓存，总是获取最新
    staleTime: 0,
  });
}

/**
 * 获取任务列表
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useTaskList({ status: 'processing' });
 * ```
 */
export function useTaskList(filters?: { status?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.tasks.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.status) params.set('status', filters.status);
      if (filters?.limit) params.set('limit', filters.limit.toString());
      const query = params.toString();
      return fetchJson<TasksResponse>(`/tasks${query ? `?${query}` : ''}`);
    },
    // 列表数据缓存 1 分钟
    staleTime: 60 * 1000,
  });
}

/**
 * 取消任务
 * 
 * @example
 * ```tsx
 * const cancelMutation = useCancelTask();
 * await cancelMutation.mutateAsync(taskId);
 * ```
 */
export function useCancelTask() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      return fetchJson<TaskResponse>(`/tasks/${taskId}/cancel`, {
        method: 'POST',
      });
    },
    // 取消成功后刷新任务详情和列表
    onSuccess: (data) => {
      const taskId = data.task.id;
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}

/**
 * 删除任务
 * 
 * @example
 * ```tsx
 * const deleteMutation = useDeleteTask();
 * await deleteMutation.mutateAsync(taskId);
 * ```
 */
export function useDeleteTask() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      return fetchJson<{ success: boolean }>(`/tasks/${taskId}`, {
        method: 'DELETE',
      });
    },
    // 删除成功后从缓存中移除
    onSuccess: (_, taskId) => {
      queryClient.removeQueries({ queryKey: queryKeys.tasks.detail(taskId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}

/**
 * 重试任务
 * 
 * @example
 * ```tsx
 * const retryMutation = useRetryTask();
 * await retryMutation.mutateAsync(taskId);
 * ```
 */
export function useRetryTask() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      return fetchJson<TaskResponse>(`/tasks/${taskId}/retry`, {
        method: 'POST',
      });
    },
    // 重试成功后刷新任务详情和列表
    onSuccess: (data) => {
      const taskId = data.task.id;
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}
