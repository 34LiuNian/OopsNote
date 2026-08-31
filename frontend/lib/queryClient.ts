import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

// Query and mutation failures are owned by the page that renders them.
// The page reports through notify.error; the global cache must not add a second path.
export const queryClient = new QueryClient({
  queryCache: new QueryCache(),
  mutationCache: new MutationCache(),
  defaultOptions: {
    queries: {
      retry: false,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: Infinity,
    },
    mutations: { retry: false },
  },
});

export const queryKeys = {
  tasks: {
    all: ["tasks"] as const,
    lists: () => [...queryKeys.tasks.all, "list"] as const,
    list: (filters?: { status?: string }) => [...queryKeys.tasks.lists(), filters] as const,
    details: () => [...queryKeys.tasks.all, "detail"] as const,
    detail: (taskId: string) => [...queryKeys.tasks.details(), taskId] as const,
    stream: (taskId: string) => [...queryKeys.tasks.detail(taskId), "stream"] as const,
  },
  problems: {
    all: ["problems"] as const,
    list: (filtersKey: string) => [...queryKeys.problems.all, "list", filtersKey] as const,
  },
  tags: {
    all: ["tags"] as const,
    lists: () => [...queryKeys.tags.all, "list"] as const,
    list: (dimension?: string, query?: string) => [...queryKeys.tags.lists(), { dimension, query }] as const,
    dimensions: () => [...queryKeys.tags.all, "dimensions"] as const,
  },
  settings: {
    all: ["settings"] as const,
    agentModels: () => [...queryKeys.settings.all, "agentModels"] as const,
    agentEnabled: () => [...queryKeys.settings.all, "agentEnabled"] as const,
    agentThinking: () => [...queryKeys.settings.all, "agentThinking"] as const,
    agentTemperature: () => [...queryKeys.settings.all, "agentTemperature"] as const,
    models: () => [...queryKeys.settings.all, "models"] as const,
    gateway: () => [...queryKeys.settings.all, "gateway"] as const,
    debug: () => [...queryKeys.settings.all, "debug"] as const,
    systemInfo: () => [...queryKeys.settings.all, "systemInfo"] as const,
    aiProfiles: () => [...queryKeys.settings.all, "aiProfiles"] as const,
    aiRuntime: () => [...queryKeys.settings.all, "aiRuntime"] as const,
  },
};
