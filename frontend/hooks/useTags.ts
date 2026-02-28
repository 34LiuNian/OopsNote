"use client";

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '../lib/api';
import type { TagsResponse } from '../types/api';
import { queryKeys } from '../lib/queryClient';

/**
 * 获取标签列表
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useTags({ dimension: 'knowledge', query: '函数' });
 * ```
 */
export function useTags(options?: {
  dimension?: string;
  query?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: queryKeys.tags.list(options?.dimension, options?.query),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (options?.dimension) params.set('dimension', options.dimension);
      if (options?.query) params.set('query', options.query);
      if (options?.limit) params.set('limit', options.limit.toString());
      const queryString = params.toString();
      return fetchJson<TagsResponse>(`/tags${queryString ? `?${queryString}` : ''}`);
    },
    // 标签数据缓存 5 分钟
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * 获取标签维度
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useTagDimensions();
 * ```
 */
export function useTagDimensionsQuery() {
  return useQuery({
    queryKey: queryKeys.tags.dimensions(),
    queryFn: () => fetchJson<{ dimensions: string[] }>('/tags/dimensions'),
    // 维度数据很少变化，缓存 1 小时
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * 创建标签
 * 
 * @example
 * ```tsx
 * const createMutation = useCreateTag();
 * await createMutation.mutateAsync({ dimension: 'knowledge', value: '新标签' });
 * ```
 */
export function useCreateTag() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (data: { dimension: string; value: string; aliases?: string[] }) => {
      return fetchJson<{ id: string }>(`/tags`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    // 创建成功后刷新标签列表
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.tags.list(variables.dimension) 
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.lists() });
    },
  });
}

/**
 * 删除标签
 * 
 * @example
 * ```tsx
 * const deleteMutation = useDeleteTag();
 * await deleteMutation.mutateAsync(tagId);
 * ```
 */
export function useDeleteTag() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (tagId: string) => {
      return fetchJson<{ success: boolean }>(`/tags/${tagId}`, {
        method: 'DELETE',
      });
    },
    // 删除成功后从缓存中移除
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.lists() });
    },
  });
}
