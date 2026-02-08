import { fetchJson } from "../../lib/api";
import type {
  ProblemsResponse,
  TaskResponse,
  TasksResponse,
} from "../../types/api";
import { API_BASE } from "../../lib/api";

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
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
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
  return fetch(`${API_BASE}/papers/compile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
