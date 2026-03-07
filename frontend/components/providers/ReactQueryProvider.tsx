"use client";

import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '../../lib/queryClient';

/**
 * React Query Provider
 * 为整个应用提供查询缓存和状态管理
 */
export function ReactQueryProvider({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
