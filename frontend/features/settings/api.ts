import { fetchJson } from "../../lib/api";
import type {
  AgentEnabledResponse,
  AgentEnabledUpdateRequest,
  AgentModelsResponse,
  AgentModelsUpdateRequest,
  AgentTemperatureResponse,
  AgentTemperatureUpdateRequest,
  AgentThinkingResponse,
  AgentThinkingUpdateRequest,
  DebugSettingsResponse,
  DebugSettingsUpdateRequest,
  GatewaySettingsResponse,
  GatewaySettingsUpdateRequest,
  GatewayTestRequest,
  GatewayTestResponse,
  ModelsResponse,
  SystemInfoResponse,
} from "../../types/api";

// ── Agent Models ─────────────────────────────────────────────────────────

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

// ── Agent Enabled ────────────────────────────────────────────────────────

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

// ── Agent Thinking ───────────────────────────────────────────────────────

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

// ── Agent Temperature ────────────────────────────────────────────────────

export async function getAgentTemperature(): Promise<AgentTemperatureResponse> {
  return fetchJson<AgentTemperatureResponse>("/settings/agent-temperature");
}

export async function updateAgentTemperature(
  payload: AgentTemperatureUpdateRequest
): Promise<AgentTemperatureResponse> {
  return fetchJson<AgentTemperatureResponse>("/settings/agent-temperature", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ── Models ───────────────────────────────────────────────────────────────

export async function listModels(refresh: boolean): Promise<ModelsResponse> {
  const query = refresh ? "?refresh=true" : "";
  return fetchJson<ModelsResponse>(`/models${query}`);
}

// ── Gateway Settings ─────────────────────────────────────────────────────

export async function getGatewaySettings(): Promise<GatewaySettingsResponse> {
  return fetchJson<GatewaySettingsResponse>("/settings/gateway");
}

export async function updateGatewaySettings(
  payload: GatewaySettingsUpdateRequest
): Promise<GatewaySettingsResponse> {
  return fetchJson<GatewaySettingsResponse>("/settings/gateway", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function testGatewayConnection(
  payload: GatewayTestRequest
): Promise<GatewayTestResponse> {
  return fetchJson<GatewayTestResponse>("/settings/gateway/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Debug Settings ───────────────────────────────────────────────────────

export async function getDebugSettings(): Promise<DebugSettingsResponse> {
  return fetchJson<DebugSettingsResponse>("/settings/debug");
}

export async function updateDebugSettings(
  payload: DebugSettingsUpdateRequest
): Promise<DebugSettingsResponse> {
  return fetchJson<DebugSettingsResponse>("/settings/debug", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ── System Info ──────────────────────────────────────────────────────────

export async function getSystemInfo(): Promise<SystemInfoResponse> {
  return fetchJson<SystemInfoResponse>("/settings/system-info");
}
