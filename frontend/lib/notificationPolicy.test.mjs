import assert from "node:assert/strict";
import test from "node:test";
import { errorNotificationId, notificationAutoClose, requestErrorMessage } from "./notificationPolicy.ts";

test("error notifications are persistent regardless of caller timeout", () => {
  assert.equal(notificationAutoClose("red", undefined), false);
  assert.equal(notificationAutoClose("red", 100), false);
  assert.equal(notificationAutoClose("red", false), false);
  assert.equal(notificationAutoClose("green", 1500), 1500);
});

test("the same failure evidence receives a stable notification id", () => {
  const first = errorNotificationId("登录失败", "用户名或密码不正确");
  const second = errorNotificationId("登录失败", "用户名或密码不正确");
  assert.equal(first, second);
  assert.match(first, /^error-[a-z0-9]+$/);
});

test("different failure kinds do not share an id when they only share a fallback description", () => {
  const first = errorNotificationId("附图设置保存失败", "请稍后重试");
  const second = errorNotificationId("题图任务提交失败", "请稍后重试");
  assert.notEqual(first, second);
});

test("explicit notification ids remain authoritative", () => {
  assert.equal(errorNotificationId("失败", "详情", "batch-operation-error"), "batch-operation-error");
});

test("request error messages prefer the thrown detail over a shared fallback", () => {
  assert.equal(requestErrorMessage(new Error("渠道不存在"), "请稍后重试"), "渠道不存在");
  assert.equal(requestErrorMessage("模型同步失败", "请稍后重试"), "模型同步失败");
  assert.equal(requestErrorMessage(undefined, "请稍后重试"), "请稍后重试");
  assert.equal(requestErrorMessage(new Error("   "), "请稍后重试"), "请稍后重试");
});
