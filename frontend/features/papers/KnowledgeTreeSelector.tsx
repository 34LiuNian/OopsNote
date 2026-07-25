"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronRight } from "lucide-react";
import { IconButton, Select } from "@/components/ui/primitives";
import type { KnowledgeTreeNode } from "../../types/api";
import styles from "../../app/papers/paperWorkflow.module.css";

function filterTree(node: KnowledgeTreeNode, query: string): KnowledgeTreeNode | null {
  if (node.scope && node.scope !== "core") return null;
  const children = node.children
    .map((child) => filterTree(child, query))
    .filter((child): child is KnowledgeTreeNode => child !== null);
  if (!query || node.title.toLocaleLowerCase().includes(query) || children.length) {
    return { ...node, children };
  }
  return null;
}

type NodeSelectionState = {
  checked: boolean;
  indeterminate: boolean;
};

function buildSelectionStates(
  node: KnowledgeTreeNode,
  selectedLeafIds: Set<string>,
  states: Map<string, NodeSelectionState>,
): { selected: number; total: number } {
  const children = node.children.filter((child) => !child.scope || child.scope === "core");
  if (!children.length) {
    const checked = selectedLeafIds.has(node.id);
    states.set(node.id, { checked, indeterminate: false });
    return { selected: checked ? 1 : 0, total: 1 };
  }

  const counts = children.reduce(
    (current, child) => {
      const childCounts = buildSelectionStates(child, selectedLeafIds, states);
      return {
        selected: current.selected + childCounts.selected,
        total: current.total + childCounts.total,
      };
    },
    { selected: 0, total: 0 },
  );
  states.set(node.id, {
    checked: counts.total > 0 && counts.selected === counts.total,
    indeterminate: counts.selected > 0 && counts.selected < counts.total,
  });
  return counts;
}

function TreeNodeRow({
  node,
  searching,
  selectionStates,
  onToggle,
}: {
  node: KnowledgeTreeNode;
  searching: boolean;
  selectionStates: Map<string, NodeSelectionState>;
  onToggle: (node: KnowledgeTreeNode) => void;
}) {
  const [expanded, setExpanded] = useState(node.depth < 2);
  const open = searching || expanded;
  const hasChildren = node.children.length > 0;
  const selectionState = selectionStates.get(node.id) ?? { checked: false, indeterminate: false };

  return (
    <li className={styles.treeItem}>
      <div className={styles.treeRow} style={{ paddingLeft: `${Math.max(0, node.depth - 1) * 14}px` }}>
        {hasChildren ? (
          <button
            type="button"
            className={styles.treeExpand}
            onClick={() => setExpanded((value) => !value)}
            aria-label={open ? `收起${node.title}` : `展开${node.title}`}
          >
            {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        ) : <span className={styles.treeSpacer} />}
        <input
          type="checkbox"
          checked={selectionState.checked}
          ref={(element) => {
            if (element) element.indeterminate = selectionState.indeterminate;
          }}
          onChange={() => onToggle(node)}
          aria-label={`选择${node.title}`}
        />
        <button
          type="button"
          className={`${styles.treeLabel}${selectionState.checked || selectionState.indeterminate ? ` ${styles.treeLabelSelected}` : ""}`}
          onClick={() => onToggle(node)}
        >
          {node.title}
        </button>
      </div>
      {hasChildren && open ? (
        <ul className={styles.treeList}>
          {node.children.map((child) => (
            <TreeNodeRow
              key={child.id}
              node={child}
              searching={searching}
              selectionStates={selectionStates}
              onToggle={onToggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function KnowledgeTreeSelector({
  root,
  subject,
  subjectOptions,
  selectedLeafIds,
  onBack,
  onSubjectChange,
  onToggle,
}: {
  root: KnowledgeTreeNode | null;
  subject: string;
  subjectOptions: Array<{ value: string; label: string }>;
  selectedLeafIds: Set<string>;
  onBack: () => void;
  onSubjectChange: (subject: string) => void;
  onToggle: (node: KnowledgeTreeNode) => void;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleRoot = useMemo(
    () => root ? filterTree(root, normalizedQuery) : null,
    [root, normalizedQuery],
  );
  const selectionStates = useMemo(() => {
    const states = new Map<string, NodeSelectionState>();
    if (root) buildSelectionStates(root, selectedLeafIds, states);
    return states;
  }, [root, selectedLeafIds]);

  return (
    <div className={styles.treePanel}>
      <div className={styles.treeSubjectBar}>
        <IconButton
          icon={ArrowLeft}
          size="small"
          variant="invisible"
          aria-label="退出正式组卷"
          title="退出正式组卷"
          onClick={onBack}
        />
        <span className={styles.treeSubjectLabel}>学科</span>
        <div className={styles.treeSubjectControl}>
          <Select value={subject} onValueChange={onSubjectChange} block>
            {subjectOptions.map((option) => (
              <Select.Option key={option.value} value={option.value}>{option.label}</Select.Option>
            ))}
          </Select>
        </div>
      </div>
      <div className={styles.treeTabs}>
        <span>章节</span>
        <span className={styles.treeTabActive}>知识点</span>
      </div>
      <input
        className={styles.treeSearch}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="搜索知识点"
        aria-label="搜索知识点"
      />
      <div className={styles.treeScroll}>
        {!root ? <div className={styles.treeEmpty}>正在载入知识树…</div> : null}
        {root && !visibleRoot ? <div className={styles.treeEmpty}>没有匹配的知识点</div> : null}
        {visibleRoot ? (
          <ul className={styles.treeList}>
            {visibleRoot.children.map((child) => (
              <TreeNodeRow
                key={child.id}
                node={child}
                searching={Boolean(normalizedQuery)}
                selectionStates={selectionStates}
                onToggle={onToggle}
              />
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
