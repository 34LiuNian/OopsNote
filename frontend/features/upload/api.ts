import { fetchApi, fetchJson, fetchRawUpload } from "../../lib/api";
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
  batch_session_hash?: string;
  batch_segment_id?: string;
  batch_page_index?: number;
  batch_question_no?: number;
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

export type BatchSessionSegment = {
  id: string;
  parts: Array<{
    page_index: number;
    x: number;
    y: number;
    width: number;
    height: number;
    order: number;
  }>;
  page_index?: number | null;
  x?: number | null;
  y?: number | null;
  width?: number | null;
  height?: number | null;
  continuation?: {
    page_index: number;
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
  question_no?: number;
  status: "pending" | "processing" | "completed" | "failed";
  task_id?: string | null;
  problem_ids: string[];
  error?: string | null;
};

export type BatchSession = {
  file_hash: string;
  filename: string;
  mime_type: string;
  asset_path: string;
  page_count: number;
  subject: string;
  notes: string;
  active_page: number;
  crop_rect: { x: number; y: number; width: number; height: number };
  crop_confirmed: boolean;
  segments: BatchSessionSegment[];
  created_at: string;
  updated_at: string;
};

export async function listBatchSessions(): Promise<BatchSession[]> {
  return (await fetchJson<{ items: BatchSession[] }>("/batch-sessions")).items;
}

export async function getBatchSession(fileHash: string): Promise<BatchSession | null> {
  const response = await fetchApi(`/batch-sessions/${encodeURIComponent(fileHash)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await response.text());
  return (await response.json() as { session: BatchSession }).session;
}

export async function uploadBatchSource(fileHash: string, file: File): Promise<BatchSession> {
  const response = await fetchRawUpload(`/batch-sessions/${encodeURIComponent(fileHash)}/source`, {
    method: "PUT",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-OopsNote-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json() as { session: BatchSession }).session;
}

export async function updateBatchSession(
  fileHash: string,
  payload: Pick<BatchSession, "page_count" | "active_page" | "crop_rect" | "crop_confirmed" | "segments">,
): Promise<BatchSession> {
  return (await fetchJson<{ session: BatchSession }>(`/batch-sessions/${encodeURIComponent(fileHash)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })).session;
}

export async function deleteBatchSession(fileHash: string): Promise<void> {
  await fetchJson(`/batch-sessions/${encodeURIComponent(fileHash)}`, { method: "DELETE" });
}
