"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button, IconButton, NativeInput } from "@/components/ui/primitives";
import type { KnowledgeTreeNode } from "@/types/api";
import {
  buildSelectionStates,
  collectExpandedIdsForSelection,
  filterTree,
  isTreeLeaf,
  type NodeSelectionState,
} from "./knowledgeTree";
import styles from "./KnowledgeTreeView.module.css";

export type KnowledgeTreeSelectionMode = "cascade" | "leaf";

function TreeNodeRow({
  node,
  searching,
  selectionMode,
  selectionStates,
  defaultExpandedIds,
  onToggle,
}: {
  node: KnowledgeTreeNode;
  searching: boolean;
  selectionMode: KnowledgeTreeSelectionMode;
  selectionStates: Map<string, NodeSelectionState>;
  defaultExpandedIds: Set<string>;
  onToggle: (node: KnowledgeTreeNode) => void;
}) {
  const [expanded, setExpanded] = useState(() => defaultExpandedIds.has(node.id));
  const open = searching || expanded;
  const leaf = isTreeLeaf(node);
  const hasChildren = !leaf;
  const selectable = selectionMode === "cascade" || leaf;
  const reserveExpandColumn = !hasChildren && selectionMode === "cascade";
  const selectionState = selectionStates.get(node.id) ?? { checked: false, indeterminate: false };

  const toggleExpand = () => {
    setExpanded((current) => !current);
  };

  const handleLabelClick = () => {
    if (!selectable) {
      toggleExpand();
      return;
    }
    onToggle(node);
  };

  return (
    <li className={styles.item}>
      <div className={styles.row} style={{ paddingLeft: `${Math.max(0, node.depth - 1) * 14}px` }}>
        {hasChildren ? (
          <IconButton
            icon={open ? ChevronDown : ChevronRight}
            size="small"
            variant="invisible"
            type="button"
            className={styles.expand}
            onClick={toggleExpand}
            aria-label={open ? `收起${node.title}` : `展开${node.title}`}
          />
        ) : reserveExpandColumn ? <span className={styles.spacer} /> : null}
        {selectable ? (
          <NativeInput
            type="checkbox"
            className={styles.checkbox}
            checked={selectionState.checked}
            ref={(element) => {
              if (element) element.indeterminate = selectionState.indeterminate;
            }}
            onChange={() => onToggle(node)}
            aria-label={`选择${node.title}`}
          />
        ) : null}
        <Button
          variant="invisible"
          type="button"
          contentAlign="start"
          className={`${styles.label}${selectionState.checked || selectionState.indeterminate ? ` ${styles.labelSelected}` : ""}`}
          onClick={handleLabelClick}
        >
          {node.title}
        </Button>
      </div>
      {hasChildren && open ? (
        <ul className={styles.list}>
          {node.children.map((child) => (
            <TreeNodeRow
              key={child.id}
              node={child}
              searching={searching}
              selectionMode={selectionMode}
              selectionStates={selectionStates}
              defaultExpandedIds={defaultExpandedIds}
              onToggle={onToggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function KnowledgeTreeView({
  root,
  selectedLeafIds,
  onToggle,
  selectionMode = "cascade",
  loadingLabel = "正在载入知识树…",
  emptyLabel = "没有匹配的知识点",
  searchPlaceholder = "搜索知识点",
  className,
}: {
  root: KnowledgeTreeNode | null;
  selectedLeafIds: Set<string>;
  onToggle: (node: KnowledgeTreeNode) => void;
  selectionMode?: KnowledgeTreeSelectionMode;
  loadingLabel?: string;
  emptyLabel?: string;
  searchPlaceholder?: string;
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleRoot = useMemo(
    () => (root ? filterTree(root, normalizedQuery) : null),
    [root, normalizedQuery],
  );
  const selectionStates = useMemo(() => {
    const states = new Map<string, NodeSelectionState>();
    if (root) buildSelectionStates(root, selectedLeafIds, states);
    return states;
  }, [root, selectedLeafIds]);
  const defaultExpandedIds = useMemo(
    () => collectExpandedIdsForSelection(root, selectedLeafIds),
    [root, selectedLeafIds],
  );

  return (
    <div className={[styles.panel, className].filter(Boolean).join(" ")}>
      <NativeInput
        className={styles.search}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={searchPlaceholder}
        aria-label={searchPlaceholder}
      />
      <div className={styles.scroll}>
        {!root ? <div className={styles.empty}>{loadingLabel}</div> : null}
        {root && !visibleRoot ? <div className={styles.empty}>{emptyLabel}</div> : null}
        {visibleRoot ? (
          <ul className={styles.list}>
            {visibleRoot.children.map((child) => (
              <TreeNodeRow
                key={child.id}
                node={child}
                searching={Boolean(normalizedQuery)}
                selectionMode={selectionMode}
                selectionStates={selectionStates}
                defaultExpandedIds={defaultExpandedIds}
                onToggle={onToggle}
              />
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
