"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Button, FormControl, Modal, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { XIcon } from "@/components/ui/icons";
import { notify } from "@/lib/notify";
import { notifyRequestError } from "@/lib/requestError";
import { SubjectChipGroup } from "@/components/SubjectChipGroup";
import { getKnowledgeTree } from "@/features/tags/api";
import type { KnowledgeTreeNode } from "@/types/api";
import { KnowledgeTreeView, type KnowledgeTreeSelectionMode } from "./KnowledgeTreeView";
import {
  cascadeDisplayNodes,
  collectLeafIds,
  compactSelectedNodeIds,
  findKnowledgeNode,
  findLeavesByTitle,
  isTreeLeaf,
  nodeTitlePath,
  selectedLeafIdsFromNodeIds,
  selectedLeafIdsFromTitles,
} from "./knowledgeTree";
import styles from "./KnowledgeLeafPicker.module.css";

const DEFAULT_MAX_KNOWLEDGE_LEAVES = 6;

type SelectedKnowledgeItem = {
  key: string;
  title: string;
  path: string[];
  inTree: boolean;
  removeValues: string[];
};

function titleKey(value: string) {
  return value.trim().toLocaleLowerCase();
}

function withoutTitles(current: string[], titles: string[]) {
  const remove = new Set(titles.map(titleKey).filter(Boolean));
  return current.filter((item) => !remove.has(titleKey(item)));
}

function withTitles(current: string[], titles: string[]) {
  const next = [...current];
  const seen = new Set(next.map(titleKey));
  for (const title of titles) {
    const key = titleKey(title);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    next.push(title);
  }
  return next;
}

function formatPath(path: string[]): { trail: string; title: string } {
  if (!path.length) return { trail: "", title: "" };
  return {
    trail: path.slice(0, -1).join(" / "),
    title: path[path.length - 1] ?? "",
  };
}

function KnowledgePathChip({
  item,
  onRemove,
  showPath,
}: {
  item: SelectedKnowledgeItem;
  onRemove: () => void;
  showPath: boolean;
}) {
  const { trail, title } = formatPath(item.path);
  return (
    <Box
      as="button"
      type="button"
      className={styles.chip}
      data-in-tree={item.inTree ? "true" : "false"}
      aria-label={`移除知识点 ${item.title}`}
      title={item.path.join(" / ")}
      onClick={onRemove}
    >
      {showPath && trail ? <span className={styles.chipPath}>{trail}</span> : null}
      <span className={styles.chipTitle}>{title}</span>
      <XIcon size={12} aria-hidden="true" />
    </Box>
  );
}

export function KnowledgeLeafPicker({
  subject,
  value,
  onChange,
  label,
  emptyLabel = "尚未标注知识点",
  missingSubjectLabel = "当前题目没有学科，无法载入知识树",
  dialogHint,
  maxSelected = DEFAULT_MAX_KNOWLEDGE_LEAVES,
  selectionMode = "leaf",
  subjectOptions,
  onSubjectChange,
}: {
  subject: string;
  value: string[];
  onChange: (next: string[]) => void;
  label?: string;
  emptyLabel?: string;
  missingSubjectLabel?: string;
  dialogHint?: string;
  maxSelected?: number | null;
  selectionMode?: KnowledgeTreeSelectionMode;
  subjectOptions?: Array<{ value: string; label: string }>;
  onSubjectChange?: (subject: string) => void;
}) {
  const [root, setRoot] = useState<KnowledgeTreeNode | null>(null);
  const [loadedSubject, setLoadedSubject] = useState("");
  const [treeError, setTreeError] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!subject) return;
    let active = true;
    void getKnowledgeTree(subject)
      .then((response) => {
        if (!active) return;
        setLoadedSubject(subject);
        setTreeError("");
        setRoot(response.subjects[subject]?.root ?? null);
      })
      .catch((reason) => {
        if (!active) return;
        setLoadedSubject(subject);
        setRoot(null);
        setTreeError(notifyRequestError("知识树加载失败", reason, "知识树加载失败"));
      });
    return () => {
      active = false;
    };
  }, [subject]);

  const treeRoot = loadedSubject === subject ? root : null;
  const canPickSubject = Boolean(subjectOptions?.length && onSubjectChange);
  const loadError = subject ? treeError : canPickSubject ? "" : missingSubjectLabel;

  const selectedLeafIds = useMemo(
    () => (
      selectionMode === "cascade"
        ? selectedLeafIdsFromNodeIds(treeRoot, value)
        : selectedLeafIdsFromTitles(treeRoot, value)
    ),
    [selectionMode, treeRoot, value],
  );
  const hint = !subject && canPickSubject
    ? "先选学科，再勾知识点。"
    : dialogHint ?? (
      selectionMode === "cascade"
        ? "可勾选父级，整枝加入筛选。多选为任意命中，不能新建知识标签。"
        : "只选择知识树叶子。父级用于浏览，点选即加入本题，不能整枝勾选或新建。"
    );

  const selectedItems = useMemo(() => {
    if (selectionMode === "cascade") {
      if (!treeRoot) {
        return value.map((id) => ({
          key: id,
          title: id,
          path: [id],
          inTree: false,
          removeValues: [id],
        }));
      }
      const { nodes, orphans } = cascadeDisplayNodes(treeRoot, value);
      const items: SelectedKnowledgeItem[] = nodes.map((node) => ({
        key: node.id,
        title: node.title,
        path: nodeTitlePath(treeRoot, node.id),
        inTree: true,
        removeValues: [node.id],
      }));
      for (const id of orphans) {
        const node = findKnowledgeNode(treeRoot, id);
        items.push({
          key: id,
          title: node?.title ?? id,
          path: node ? nodeTitlePath(treeRoot, node.id) : [id],
          inTree: Boolean(node),
          removeValues: [id],
        });
      }
      return items;
    }
    return value.map((title) => {
      const leaf = treeRoot ? findLeavesByTitle(treeRoot, title)[0] ?? null : null;
      const path = leaf && treeRoot ? nodeTitlePath(treeRoot, leaf.id) : [title];
      return {
        key: title,
        title,
        path,
        inTree: Boolean(leaf),
        removeValues: [title],
      };
    });
  }, [selectionMode, treeRoot, value]);

  const removeValues = useCallback((values: string[]) => {
    if (selectionMode === "cascade" && treeRoot) {
      const nextLeaves = new Set(selectedLeafIds);
      for (const id of values) {
        const node = findKnowledgeNode(treeRoot, id);
        if (node) {
          for (const leafId of collectLeafIds(node)) nextLeaves.delete(leafId);
        } else {
          nextLeaves.delete(id);
        }
      }
      onChange(compactSelectedNodeIds(treeRoot, nextLeaves));
      return;
    }
    onChange(withoutTitles(value, values));
  }, [onChange, selectedLeafIds, selectionMode, treeRoot, value]);

  const toggleNode = useCallback((node: KnowledgeTreeNode) => {
    const fullNode = treeRoot ? findKnowledgeNode(treeRoot, node.id) ?? node : node;
    if (selectionMode === "leaf") {
      if (!isTreeLeaf(fullNode)) return;
      const title = fullNode.title.trim();
      if (!title) return;
      if (value.some((item) => titleKey(item) === titleKey(title))) {
        onChange(withoutTitles(value, [title]));
        return;
      }
      if (maxSelected != null && value.length >= maxSelected) {
        notify.error({ title: `知识点最多选择 ${maxSelected} 个` });
        return;
      }
      onChange(withTitles(value, [title]));
      return;
    }
    if (!treeRoot) return;
    const leafIds = collectLeafIds(fullNode);
    if (!leafIds.length) return;
    const nextLeaves = new Set(selectedLeafIds);
    const fullySelected = leafIds.every((id) => nextLeaves.has(id));
    for (const id of leafIds) {
      if (fullySelected) nextLeaves.delete(id);
      else nextLeaves.add(id);
    }
    onChange(compactSelectedNodeIds(treeRoot, nextLeaves));
  }, [maxSelected, onChange, selectedLeafIds, selectionMode, treeRoot, value]);

  const pickAction = (
    <Button size="small" variant="secondary" onClick={() => setOpen(true)}>
      选择知识点
    </Button>
  );
  const chipList = (
    <Box className={styles.chips}>
      {selectedItems.length ? selectedItems.map((item) => (
        <KnowledgePathChip
          key={item.key}
          item={item}
          showPath={selectionMode !== "cascade"}
          onRemove={() => removeValues(item.removeValues)}
        />
      )) : (
        <Text className={styles.empty}>{emptyLabel}</Text>
      )}
    </Box>
  );

  return (
    <Box className={styles.shell}>
      {label ? (
        <>
          <Box className={styles.fieldHeader}>
            <FormControl.Label>{label}</FormControl.Label>
            {pickAction}
          </Box>
          {chipList}
        </>
      ) : (
        <Box className={styles.summary}>
          {chipList}
          {pickAction}
        </Box>
      )}
      <ErrorBanner message={loadError} title="知识树加载失败" />
      <Modal
        opened={open}
        onClose={() => setOpen(false)}
        title="选择知识点"
        centered
        size="lg"
        radius="lg"
      >
        <Box className={styles.dialog}>
          <Text className={styles.hint}>{hint}</Text>
          {subjectOptions && onSubjectChange ? (
            <SubjectChipGroup
              value={subject}
              onChange={onSubjectChange}
              options={subjectOptions}
              layout="spread"
              aria-label="弹层学科"
            />
          ) : null}
          <Box className={styles.dialogTree}>
            {!subject ? (
              <div className={styles.placeholder}>选择学科后显示知识树</div>
            ) : loadedSubject !== subject ? (
              <KnowledgeTreeView
                root={null}
                selectedLeafIds={selectedLeafIds}
                onToggle={toggleNode}
                selectionMode={selectionMode}
              />
            ) : treeRoot ? (
              <KnowledgeTreeView
                root={treeRoot}
                selectedLeafIds={selectedLeafIds}
                onToggle={toggleNode}
                selectionMode={selectionMode}
                emptyLabel="知识树中没有此项"
              />
            ) : (
              <div className={styles.placeholder}>当前学科没有知识树</div>
            )}
          </Box>
          <Box className={styles.dialogFooter}>
            <Box className={styles.chips}>
              {selectedItems.length ? selectedItems.map((item) => (
                <KnowledgePathChip
                  key={`dialog:${item.key}`}
                  item={item}
                  showPath={selectionMode !== "cascade"}
                  onRemove={() => removeValues(item.removeValues)}
                />
              )) : <Text className={styles.empty}>尚未选择</Text>}
            </Box>
            <Button size="small" variant="primary" onClick={() => setOpen(false)}>完成</Button>
          </Box>
        </Box>
      </Modal>
    </Box>
  );
}
