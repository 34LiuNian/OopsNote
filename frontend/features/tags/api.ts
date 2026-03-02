import { fetchJson } from "../../lib/api";
import type {
  TagDimension,
  TagDimensionsResponse,
  TagDimensionsUpdateRequest,
  TagsResponse,
} from "../../types/api";

export async function getTagDimensions(): Promise<TagDimensionsResponse> {
  return fetchJson<TagDimensionsResponse>("/settings/tag-dimensions");
}

export async function updateTagDimensions(
  payload: TagDimensionsUpdateRequest
): Promise<TagDimensionsResponse> {
  return fetchJson<TagDimensionsResponse>("/settings/tag-dimensions", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function searchTags(params: {
  dimension?: TagDimension;
  query?: string;
  limit?: number;
}): Promise<TagsResponse> {
  const sp = new URLSearchParams();
  if (params.dimension) sp.set("dimension", params.dimension);
  if (params.query && params.query.trim()) sp.set("query", params.query.trim());
  sp.set("limit", String(params.limit ?? 100));
  return fetchJson<TagsResponse>(`/tags?${sp.toString()}`);
}

export async function createTag(payload: {
  dimension: TagDimension;
  value: string;
  aliases?: string[];
}): Promise<TagsResponse> {
  return fetchJson<TagsResponse>("/tags", {
    method: "POST",
    body: JSON.stringify({
      dimension: payload.dimension,
      value: payload.value,
      aliases: Array.isArray(payload.aliases) ? payload.aliases : [],
    }),
  });
}

export async function deleteTag(tagId: string): Promise<{ ok: boolean; tag_id: string }> {
  return fetchJson<{ ok: boolean; tag_id: string }>(`/tags/${tagId}`, {
    method: "DELETE",
  });
}

export async function updateTag(
  tagId: string,
  payload: { value: string }
): Promise<TagsResponse> {
  return fetchJson<TagsResponse>(`/tags/${tagId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function mergeTags(
  sourceId: string,
  targetId: string
): Promise<{ ok: boolean; tasks_modified: number; fields_modified: number }> {
  return fetchJson<{ ok: boolean; tasks_modified: number; fields_modified: number }>(
    `/tags/${sourceId}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ target_id: targetId }),
    }
  );
}
