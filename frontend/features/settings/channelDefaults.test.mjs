import assert from "node:assert/strict";
import test from "node:test";

import { baseUrlAfterProviderChange } from "./channelDefaults.ts";

test("provider changes preserve a custom base URL", () => {
  assert.equal(
    baseUrlAfterProviderChange("deepseek", "https://gateway.example/v1", "openai-compatible"),
    "https://gateway.example/v1",
  );
});

test("provider changes replace the previous official default", () => {
  assert.equal(
    baseUrlAfterProviderChange("deepseek", "https://api.deepseek.com/v1/", "openai"),
    "https://api.openai.com/v1",
  );
});

test("openai-compatible remains incomplete until a base URL is supplied", () => {
  assert.equal(
    baseUrlAfterProviderChange("deepseek", "https://api.deepseek.com/v1", "openai-compatible"),
    null,
  );
});
