import { fetchJson } from "../../lib/api";
import type {
  AgentEnabledResponse,
  AgentEnabledUpdateRequest,
  AgentModelsResponse,
  AgentModelsUpdateRequest,
  AgentThinkingResponse,
  AgentThinkingUpdateRequest,
  ModelsResponse,
} from "../../types/api";

export async function getAgentModels(): Promise<AgentModelsResponse> {
  return fetchJson<AgentModelsResponse>("/settings/agent-models");
}

export async function updateAgentModels(
  payload: AgentModelsUpdateRequest
): Promise<AgentModelsResponse> {
  return fetchJson<AgentModelsResponse>("/settings/agent-models", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getAgentEnabled(): Promise<AgentEnabledResponse> {
  return fetchJson<AgentEnabledResponse>("/settings/agent-enabled");
}

export async function updateAgentEnabled(
  payload: AgentEnabledUpdateRequest
): Promise<AgentEnabledResponse> {
  return fetchJson<AgentEnabledResponse>("/settings/agent-enabled", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getAgentThinking(): Promise<AgentThinkingResponse> {
  return fetchJson<AgentThinkingResponse>("/settings/agent-thinking");
}

export async function updateAgentThinking(
  payload: AgentThinkingUpdateRequest
): Promise<AgentThinkingResponse> {
  return fetchJson<AgentThinkingResponse>("/settings/agent-thinking", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function listModels(refresh: boolean): Promise<ModelsResponse> {
  const query = refresh ? "?refresh=true" : "";
  return fetchJson<ModelsResponse>(`/models${query}`);
}
