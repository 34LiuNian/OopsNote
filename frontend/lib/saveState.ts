export type SavePresentation = "saving" | "failed" | "dirty" | "saved";

export function presentSaveState(
  isSaving: boolean,
  failed: boolean,
  isDirty: boolean,
): SavePresentation {
  if (isSaving) return "saving";
  if (failed) return "failed";
  if (isDirty) return "dirty";
  return "saved";
}

export function presentImmediateSaveState(
  isWriting: boolean,
  failed: boolean,
  busy: boolean,
): SavePresentation {
  if (isWriting) return "saving";
  if (failed) return "failed";
  if (busy) return "dirty";
  return "saved";
}

export const PROOFREAD_SAVE_LABEL: Record<SavePresentation, string> = {
  saving: "保存中",
  failed: "保存失败",
  dirty: "未保存",
  saved: "已保存",
};

export const DIAGRAM_SAVE_LABEL: Record<SavePresentation, string> = {
  saving: "正在保存",
  failed: "保存失败",
  dirty: "附图处理中",
  saved: "附图设置已即时保存",
};
