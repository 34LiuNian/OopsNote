"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryClient";
import {
  activateAiProfile,
  activateOcrProfile,
  createAiProfile,
  deleteAiCredential,
  deleteAiProfile,
  getAiProfiles,
  testAiProfile,
  updateAiCredential,
  updateAiProfile,
} from "./api";
import type { AiProfileDraft } from "./types";

export function useAiProfiles() {
  return useQuery({ queryKey: queryKeys.settings.aiProfiles(), queryFn: getAiProfiles });
}

export function useAiProviderMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiProfiles() });
  return {
    create: useMutation({ mutationFn: createAiProfile, onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ profileId, payload }: { profileId: string; payload: Omit<AiProfileDraft, "id"> }) => updateAiProfile(profileId, payload), onSuccess: refresh }),
    credential: useMutation({ mutationFn: ({ profileId, secret }: { profileId: string; secret: string }) => updateAiCredential(profileId, secret), onSuccess: refresh }),
    deleteCredential: useMutation({ mutationFn: deleteAiCredential, onSuccess: refresh }),
    test: useMutation({ mutationFn: testAiProfile, onSuccess: refresh }),
    remove: useMutation({ mutationFn: deleteAiProfile, onSuccess: refresh }),
    activate: useMutation({ mutationFn: activateAiProfile, onSuccess: refresh }),
    activateOcr: useMutation({ mutationFn: activateOcrProfile, onSuccess: refresh }),
  };
}
