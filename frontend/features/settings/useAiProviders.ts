"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryClient";
import { activateAiProfile, activateOcrProfile, createAiProfile, getAiProfiles, rotateAiCredential } from "./api";

export function useAiProfiles() {
  return useQuery({ queryKey: queryKeys.settings.aiProfiles(), queryFn: getAiProfiles });
}

export function useAiProviderMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiProfiles() });
  return {
    create: useMutation({ mutationFn: createAiProfile, onSuccess: refresh }),
    rotate: useMutation({ mutationFn: ({ profileId, secret }: { profileId: string; secret: string }) => rotateAiCredential(profileId, secret), onSuccess: refresh }),
    activate: useMutation({ mutationFn: activateAiProfile, onSuccess: refresh }),
    activateOcr: useMutation({ mutationFn: activateOcrProfile, onSuccess: refresh }),
  };
}
