import assert from "node:assert/strict";
import test from "node:test";

import {
  policyModelUnavailableReason,
  updatePolicyStage,
} from "./modelOptions.ts";

test("first stage edit preserves the other server selections", () => {
  const serverPolicy = {
    version: 4,
    updated_at: "2026-08-05T00:00:00Z",
    vision: { channel_id: "vision-channel", model_id: "vision-model" },
    agent: { channel_id: "agent-channel", model_id: "agent-model" },
    review: { channel_id: "review-channel", model_id: "review-model" },
    diagram: { channel_id: "diagram-channel", model_id: "diagram-model" },
  };

  const updated = updatePolicyStage(
    serverPolicy,
    "vision",
    { channel_id: "replacement", model_id: "replacement-model" },
  );

  assert.deepEqual(updated.agent, serverPolicy.agent);
  assert.deepEqual(updated.review, serverPolicy.review);
  assert.deepEqual(updated.diagram, serverPolicy.diagram);
  assert.deepEqual(updated.vision, { channel_id: "replacement", model_id: "replacement-model" });
  assert.notEqual(updated, serverPolicy);
});

test("policy picker eligibility rejects every unavailable boundary", () => {
  const model = {
    id: "model",
    source: "provider",
    enabled: true,
    capability: { tool_calling: true, vision: true },
    discovered_at: null,
  };
  const channel = {
    id: "channel",
    version: 1,
    display_name: "Channel",
    provider: "deepseek",
    base_url: null,
    enabled: true,
    has_secret: true,
    models: [model],
    created_at: null,
    updated_at: null,
    secret_updated_at: null,
    policy_stages: [],
  };

  assert.equal(policyModelUnavailableReason(channel, model, "vision"), null);
  assert.equal(policyModelUnavailableReason({ ...channel, enabled: false }, model, "vision"), "渠道已停用");
  assert.equal(policyModelUnavailableReason({ ...channel, has_secret: false }, model, "vision"), "渠道缺少访问凭据");
  assert.equal(policyModelUnavailableReason(channel, { ...model, enabled: false }, "vision"), "模型未启用");
  assert.equal(policyModelUnavailableReason(channel, { ...model, capability: { ...model.capability, vision: false } }, "vision"), "未启用 Vision 能力");
  assert.equal(policyModelUnavailableReason(channel, { ...model, capability: { ...model.capability, tool_calling: false } }, "agent"), "未启用 Tool Calling");
});
