import assert from "node:assert/strict";
import test from "node:test";
import { presentImmediateSaveState, presentSaveState } from "./saveState.ts";

test("proofread save state never reports saved after a failed write", () => {
  assert.equal(presentSaveState(true, true, true), "saving");
  assert.equal(presentSaveState(false, true, true), "failed");
  assert.equal(presentSaveState(false, false, true), "dirty");
  assert.equal(presentSaveState(false, false, false), "saved");
});

test("immediate diagram writes do not look saved while in flight or failed", () => {
  assert.equal(presentImmediateSaveState(true, true, true), "saving");
  assert.equal(presentImmediateSaveState(false, true, true), "failed");
  assert.equal(presentImmediateSaveState(false, false, true), "dirty");
  assert.equal(presentImmediateSaveState(false, false, false), "saved");
});
