import { fetchJson } from "../../lib/api";
import type {
  ProblemsResponse,
  TaskResponse,
  TaskStatus,
  TasksResponse,
} from "../../types/api";
import { API_BASE } from "../../lib/api";
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
  return fetchJson<TasksResponse>(query ? `/tasks?${query}` : "/tasks");
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
  options: Array<{ key: string; text: string }>;
  knowledge_tags: string[];
  error_tags: string[];
  user_tags: string[];
  diagram_detected?: boolean;
  diagram_kind?: string | null;
  diagram_tikz_source?: string | null;
  diagram_svg?: string | null;
  diagram_render_status?: string | null;
  diagram_error?: string | null;
  diagram_needs_review?: boolean;
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

export async function rerenderProblemDiagram(taskId: string, problemId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/problems/${encodeURIComponent(problemId)}/diagram`, {
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

export async function compileTikzToSvg(content: string): Promise<string> {
  const response = await fetchApi("/latex/tikz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, inline: false }),
  });

  if (!response.ok) {
    const rawText = await response.text();
    let message = rawText;
    try {
      const parsed = JSON.parse(rawText) as {
        detail?: string | { message?: string; log?: string };
      };
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (parsed.detail && typeof parsed.detail === "object") {
        const detailMessage = parsed.detail.message || "TikZ 编译失败";
        const detailLog = parsed.detail.log || "";
        message = detailLog ? `${detailMessage}\n${detailLog}` : detailMessage;
      }
    } catch {
      message = rawText;
    }

    throw new Error(message.replace(/\\n/g, "\n"));
  }

  return await response.text();
}
