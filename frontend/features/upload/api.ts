import { fetchJson } from "../../lib/api";
import type { TaskResponse } from "../../types/api";

export type CreateUploadTaskPayload = {
  subject: string;
  notes: string;
  question_no?: string;
  source?: string;
  question_type?: string;
  difficulty?: string;
  knowledge_tags: string[];
  error_tags: string[];
  user_tags: string[];
  image_base64: string;
  filename: string;
  mime_type: string;
};

export async function createUploadTask(payload: CreateUploadTaskPayload): Promise<TaskResponse> {
  return fetchJson<TaskResponse>("/upload?auto_process=false", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function processTaskInBackground(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/process?background=true`, {
    method: "POST",
  });
}

export async function createUploadTaskAndProcess(payload: CreateUploadTaskPayload): Promise<TaskResponse> {
  const created = await createUploadTask(payload);
  const taskId = created.task.id;
  await processTaskInBackground(taskId);
  return created;
}