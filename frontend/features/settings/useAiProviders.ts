"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryClient";
import {
  createChannel,
  deleteChannel,
  getChannels,
  syncChannelModels,
  updateChannel,
  updateChannelCredential,
  updateChannelModel,
  updatePolicy,
} from "./api";
import type { ChannelDraft, LangChainPolicy } from "./types";

export function useAiChannels(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.aiProfiles(),
    queryFn: getChannels,
    enabled,
  });
}

export function useAiChannelMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiProfiles() });
  return {
    create: useMutation({ mutationFn: createChannel, onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ channelId, payload }: { channelId: string; payload: Partial<Omit<ChannelDraft, "id">> }) => updateChannel(channelId, payload), onSuccess: refresh }),
    credential: useMutation({ mutationFn: ({ channelId, secret }: { channelId: string; secret: string }) => updateChannelCredential(channelId, secret), onSuccess: refresh }),
    sync: useMutation({ mutationFn: syncChannelModels, onSuccess: refresh }),
    model: useMutation({ mutationFn: ({ channelId, modelId, payload }: { channelId: string; modelId: string; payload: Parameters<typeof updateChannelModel>[2] }) => updateChannelModel(channelId, modelId, payload), onSuccess: refresh }),
    policy: useMutation({ mutationFn: updatePolicy, onSuccess: refresh }),
    remove: useMutation({ mutationFn: deleteChannel, onSuccess: refresh }),
  };
}
