import { fetchJson } from "../../lib/api";
import type {
  ContentFormat,
  DiagramImageTone,
  NormalizedRect,
  ProblemsResponse,
  TaskResponse,
  TaskStatus,
  TasksResponse,
} from "../../types/api";
import { fetchApi } from "../../lib/api";

export type ListTasksParams = {
  active_only?: boolean;
  status?: TaskStatus;
  subject?: string;
  query?: string;
  limit?: number;
};

function toSearchParams(params?: Record<string, unknown>) {
  const sp = new URLSearchParams();
  if (!params) return sp;
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) {
      // Handle arrays by adding each value with the same key
      for (const item of v) {
        if (item === undefined || item === null || item === "") continue;
        sp.append(k, String(item));
      }
    } else if (v !== "") {
      sp.set(k, String(v));
    }
  }
  return sp;
}

export async function listTasks(params?: ListTasksParams): Promise<TasksResponse> {
  const sp = toSearchParams(params);
  const query = sp.toString();
  return fetchJson<TasksResponse>(
    query ? `/tasks?${query}` : "/tasks",
  );
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`);
}

export async function retryTask(taskId: string, background = true): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(
    `/tasks/${encodeURIComponent(taskId)}/retry?background=${background ? "true" : "false"}`,
    { method: "POST" },
  );
}

export type OverrideProblemPayload = {
  question_no: string | null;
  source: string | null;
  problem_text: string;
  content_format?: ContentFormat;
  options: string[];
  knowledge_tags: string[];
  error_tags: string[];
  user_tags: string[];
  diagram_detected?: boolean;
  diagram_kind?: string | null;
  diagram_tikz_source?: string | null;
  diagram_svg?: string | null;
  diagram_image_path?: string | null;
  diagram_image_crop?: NormalizedRect | null;
  diagram_image_tone?: DiagramImageTone;
  diagram_position?: "left" | "right";
  diagram_scale_percent?: number | null;
  diagram_render_status?: string | null;
  diagram_error?: string | null;
  diagram_needs_review?: boolean;
};

export async function overrideProblem(
  taskId: string,
  payload: OverrideProblemPayload,
): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/problem/override`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function rerenderProblemDiagram(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/problem/diagram`, {
    method: "POST",
  });
}

export async function deleteTask(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}

export type ListProblemsParams = {
  subject?: string;
  tag?: string;
  source?: string | string[];
  knowledge_tag?: string | string[];
  error_tag?: string | string[];
  user_tag?: string | string[];
  created_after?: string;
  created_before?: string;
};

export async function listProblems(params?: ListProblemsParams): Promise<ProblemsResponse> {
  const sp = toSearchParams(params);
  const query = sp.toString();
  return fetchJson<ProblemsResponse>(query ? `/problems?${query}` : "/problems");
}

export type PaperCompilePayload = {
  items: Array<{ task_id: string; problem_id: string }>;
  title?: string;
  subtitle?: string;
  show_answers?: boolean;
};

export async function compilePaper(payload: PaperCompilePayload): Promise<Response> {
  return fetchApi("/papers/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
