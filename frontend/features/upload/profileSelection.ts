import { fetchJson } from "@/lib/api";
import { createUploadTask, type CreateUploadTaskPayload } from "./api";

export type TaskProviderOption = {
  id: string;
  display_name: string;
  provider: string;
  model: string;
  is_default: boolean;
};

export async function getTaskProviderOptions(): Promise<TaskProviderOption[]> {
  return (await fetchJson<{ items: TaskProviderOption[] }>("/ai/provider-options")).items;
}

export async function createUploadTaskAndProcessWithProfile(
  payload: CreateUploadTaskPayload,
  profileId: string | null,
) {
  const created = await createUploadTask(payload);
  const suffix = profileId ? `&profile_id=${encodeURIComponent(profileId)}` : "";
  await fetchJson(`/tasks/${encodeURIComponent(created.task.id)}/process?background=true${suffix}`, {
    method: "POST",
  });
  return created;
}
