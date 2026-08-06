"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryClient";
import {
  createChannel,
  checkChannel,
  deleteChannel,
  getChannels,
  syncChannelModels,
  updateChannel,
  updateChannelCredential,
  updateChannelModel,
  updatePolicy,
  reorderChannels,
} from "./api";
import type { ChannelDraft, ChannelsResponse, LangChainPolicy } from "./types";

export function useAiChannels(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.aiProfiles(),
    queryFn: getChannels,
    enabled,
  });
}

export function useAiChannelMutations() {
  const queryClient = useQueryClient();
  const channelsKey = queryKeys.settings.aiProfiles();
  const refresh = () => queryClient.invalidateQueries({ queryKey: channelsKey });
  return {
    create: useMutation({ mutationFn: createChannel, onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ channelId, payload }: { channelId: string; payload: Partial<Omit<ChannelDraft, "id">> }) => updateChannel(channelId, payload), onSuccess: refresh }),
    credential: useMutation({ mutationFn: ({ channelId, secret }: { channelId: string; secret: string }) => updateChannelCredential(channelId, secret), onSuccess: refresh }),
    sync: useMutation({ mutationFn: syncChannelModels, onSuccess: refresh }),
    check: useMutation({ mutationFn: ({ channelId, modelId }: { channelId: string; modelId: string }) => checkChannel(channelId, modelId) }),
    reorder: useMutation({
      mutationFn: reorderChannels,
      onMutate: async (channelIds) => {
        await queryClient.cancelQueries({ queryKey: channelsKey });
        const previous = queryClient.getQueryData<ChannelsResponse>(channelsKey);
        queryClient.setQueryData<ChannelsResponse>(channelsKey, (current) => {
          if (!current) return current;
          const byId = new Map(current.items.map((channel) => [channel.id, channel]));
          return { ...current, items: channelIds.map((id) => byId.get(id)).filter((channel): channel is NonNullable<typeof channel> => Boolean(channel)) };
        });
        return { previous };
      },
      onError: (_error, _channelIds, context) => {
        if (context?.previous) queryClient.setQueryData(channelsKey, context.previous);
      },
      onSuccess: (result) => {
        queryClient.setQueryData<ChannelsResponse>(channelsKey, (current) => current ? { ...current, items: result.items } : current);
      },
    }),
    model: useMutation({ mutationFn: ({ channelId, modelId, payload }: { channelId: string; modelId: string; payload: Parameters<typeof updateChannelModel>[2] }) => updateChannelModel(channelId, modelId, payload), onSuccess: refresh }),
    policy: useMutation({ mutationFn: updatePolicy, onSuccess: refresh }),
    remove: useMutation({ mutationFn: deleteChannel, onSuccess: refresh }),
  };
}
