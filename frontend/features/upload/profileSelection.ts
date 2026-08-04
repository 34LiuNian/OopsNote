import { fetchJson } from "@/lib/api";
import { createUploadTask, type CreateUploadTaskPayload } from "./api";

export async function createUploadTaskAndProcess(payload: CreateUploadTaskPayload) {
  const created = await createUploadTask(payload);
  await fetchJson(`/tasks/${encodeURIComponent(created.task.id)}/process?background=true`, {
    method: "POST",
  });
  return created;
}
