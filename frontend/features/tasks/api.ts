import { fetchJson } from "../../lib/api";
import type {
  ProblemsResponse,
  TaskResponse,
  TasksResponse,
} from "../../types/api";
import { API_BASE } from "../../lib/api";
import { fetchApi } from "../../lib/api";

export type ListTasksParams = {
  active_only?: boolean;
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
  return fetchJson<TasksResponse>(query ? `/tasks?${query}` : "/tasks");
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`);
}

export type OverrideProblemPayload = {
  question_no: string | null;
  source: string | null;
  problem_text: string;
  options: Array<{ key: string; text: string }>;
  knowledge_tags: string[];
  error_tags: string[];
  user_tags: string[];
};

export async function overrideProblem(
  taskId: string,
  problemId: string,
  payload: OverrideProblemPayload,
): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/problems/${encodeURIComponent(problemId)}/override`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteProblem(taskId: string, problemId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/problems/${encodeURIComponent(problemId)}`, {
    method: "DELETE",
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
