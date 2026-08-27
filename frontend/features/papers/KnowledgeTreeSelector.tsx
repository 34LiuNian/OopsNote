"use client";

import { ArrowLeft } from "lucide-react";
import { IconButton, Select } from "@/components/ui/primitives";
import { KnowledgeTreeView } from "@/components/knowledge-tree";
import type { KnowledgeTreeNode } from "../../types/api";
import styles from "../../app/papers/paperWorkflow.module.css";

export function KnowledgeTreeSelector({
  root,
  subject,
  subjectOptions,
  selectedLeafIds,
  onBack,
  onSubjectChange,
  onToggle,
  showBackButton = true,
}: {
  root: KnowledgeTreeNode | null;
  subject: string;
  subjectOptions: Array<{ value: string; label: string }>;
  selectedLeafIds: Set<string>;
  onBack: () => void;
  onSubjectChange: (subject: string) => void;
  onToggle: (node: KnowledgeTreeNode) => void;
  showBackButton?: boolean;
}) {
  return (
    <div className={styles.treePanel}>
      <div className={styles.treeSubjectBar}>
        {showBackButton ? (
          <IconButton
            icon={ArrowLeft}
            size="small"
            variant="invisible"
            aria-label="退出正式组卷"
            title="退出正式组卷"
            onClick={onBack}
          />
        ) : null}
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
      <div className={styles.treeSelectorBody}>
        <KnowledgeTreeView
          root={root}
          selectedLeafIds={selectedLeafIds}
          onToggle={onToggle}
          selectionMode="cascade"
        />
      </div>
    </div>
  );
}
