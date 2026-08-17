import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, isRetryableApiError } from "./apiError.ts";

test("only explicit transient API failures are retryable", () => {
  const transient = new ApiError("服务暂不可用", 503, {
    category: "model_request",
    code: "provider_unavailable",
    message: "服务暂不可用",
    retryable: true,
    scope: "task",
  });
  const deterministic = new ApiError("题目不存在", 404, {
    category: "request",
    code: "task_not_found",
    message: "题目不存在",
    retryable: false,
    scope: "task",
  });

  assert.equal(isRetryableApiError(transient), true);
  assert.equal(isRetryableApiError(deterministic), false);
  assert.equal(isRetryableApiError(new Error("network")), false);
});
