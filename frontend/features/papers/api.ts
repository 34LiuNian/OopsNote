import { fetchJson } from "../../lib/api";
import type {
  DifficultyBand,
  PaperDraft,
  PaperDraftItem,
  PaperDraftResponse,
  PaperDraftsResponse,
  ProblemSummary,
  ProblemsResponse,
} from "../../types/api";

export type CreatePaperPayload = {
  title: string;
  subject: string;
  knowledge_tags: string[];
  knowledge_node_ids: string[];
  difficulty_preset: string;
  difficulty_distribution: Record<DifficultyBand, number>;
  requested_counts: Record<string, number>;
  auto_select: boolean;
};

export async function createPaper(payload: CreatePaperPayload): Promise<PaperDraft> {
  return (await fetchJson<PaperDraftResponse>("/papers", {
    method: "POST",
    body: JSON.stringify(payload),
  })).paper;
}

export async function listPapers(): Promise<PaperDraftsResponse> {
  return fetchJson<PaperDraftsResponse>("/papers");
}

export async function getPaper(draftId: string): Promise<PaperDraft> {
  return (await fetchJson<PaperDraftResponse>(`/papers/${encodeURIComponent(draftId)}`)).paper;
}

export async function updatePaper(
  draftId: string,
  payload: Partial<Pick<PaperDraft, "title" | "knowledge_tags" | "knowledge_node_ids" | "difficulty_preset" | "difficulty_distribution" | "requested_counts">> & {
    items?: Array<Omit<PaperDraftItem, "problem">>;
  },
): Promise<PaperDraft> {
  return (await fetchJson<PaperDraftResponse>(`/papers/${encodeURIComponent(draftId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })).paper;
}

export async function deletePaper(draftId: string): Promise<void> {
  await fetchJson(`/papers/${encodeURIComponent(draftId)}`, { method: "DELETE" });
}

export async function listPaperCandidates(params: {
  subject: string;
  knowledgeTags?: string[];
  knowledgeNodeIds?: string[];
  limit?: number;
}): Promise<Array<ProblemSummary & { difficulty_coefficient?: number | null }>> {
  const sp = new URLSearchParams({ subject: params.subject, limit: String(params.limit ?? 250) });
  params.knowledgeTags?.forEach((tag) => sp.append("knowledge_tag", tag));
  params.knowledgeNodeIds?.forEach((id) => sp.append("knowledge_node_id", id));
  return (await fetchJson<ProblemsResponse>(`/papers/candidates?${sp.toString()}`)).items;
}
