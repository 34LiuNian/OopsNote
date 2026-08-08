import assert from "node:assert/strict";
import test from "node:test";
import { errorNotificationId, notificationAutoClose } from "./notificationPolicy.ts";

test("error notifications are persistent regardless of caller timeout", () => {
  assert.equal(notificationAutoClose("red", undefined), false);
  assert.equal(notificationAutoClose("red", 100), false);
  assert.equal(notificationAutoClose("red", false), false);
  assert.equal(notificationAutoClose("green", 1500), 1500);
});

test("the same failure evidence receives a stable notification id", () => {
  const first = errorNotificationId("登录失败", "用户名或密码不正确");
  const second = errorNotificationId("认证失败", "用户名或密码不正确");
  assert.equal(first, second);
  assert.match(first, /^error-[a-z0-9]+$/);
});

test("explicit notification ids remain authoritative", () => {
  assert.equal(errorNotificationId("失败", "详情", "batch-operation-error"), "batch-operation-error");
});
