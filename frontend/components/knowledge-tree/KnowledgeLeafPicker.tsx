"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Button, IconButton, Modal, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { XIcon } from "@/components/ui/icons";
import { notify } from "@/lib/notify";
import { getKnowledgeTree } from "@/features/tags/api";
import type { KnowledgeTreeNode } from "@/types/api";
import { KnowledgeTreeView } from "./KnowledgeTreeView";
import {
  findKnowledgeNode,
  findLeavesByTitle,
  isTreeLeaf,
  nodeTitlePath,
  selectedLeafIdsFromTitles,
} from "./knowledgeTree";
import styles from "./KnowledgeLeafPicker.module.css";

const MAX_KNOWLEDGE_LEAVES = 6;

function formatPath(path: string[]): { trail: string; title: string } {
  if (!path.length) return { trail: "", title: "" };
  return {
    trail: path.slice(0, -1).join(" / "),
    title: path[path.length - 1] ?? "",
  };
}

export function KnowledgeLeafPicker({
  subject,
  value,
  onChange,
}: {
  subject: string;
  value: string[];
  onChange: (next: string[]) => void;
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
        const trees = Object.values(response.subjects);
        setLoadedSubject(subject);
        setTreeError("");
        setRoot(response.subjects[subject]?.root ?? trees[0]?.root ?? null);
      })
      .catch((reason) => {
        if (!active) return;
        setLoadedSubject(subject);
        setRoot(null);
        setTreeError(reason instanceof Error ? reason.message : "知识树加载失败");
      });
    return () => {
      active = false;
    };
  }, [subject]);

  const treeRoot = loadedSubject === subject ? root : null;
  const loadError = subject ? treeError : "当前题目没有学科，无法载入知识树";

  const selectedLeafIds = useMemo(
    () => selectedLeafIdsFromTitles(treeRoot, value),
    [treeRoot, value],
  );

  const selectedItems = useMemo(() => {
    return value.map((title) => {
      const leaf = treeRoot ? findLeavesByTitle(treeRoot, title)[0] ?? null : null;
      const path = leaf && treeRoot ? nodeTitlePath(treeRoot, leaf.id) : [title];
      return { title, path, inTree: Boolean(leaf) };
    });
  }, [treeRoot, value]);

  const removeTitle = useCallback((title: string) => {
    onChange(value.filter((item) => item !== title));
  }, [onChange, value]);

  const toggleNode = useCallback((node: KnowledgeTreeNode) => {
    const fullNode = treeRoot ? findKnowledgeNode(treeRoot, node.id) ?? node : node;
    if (!isTreeLeaf(fullNode)) return;
    const title = fullNode.title.trim();
    if (!title) return;
    const selected = value.some((item) => item.toLocaleLowerCase() === title.toLocaleLowerCase());
    if (selected) {
      onChange(value.filter((item) => item.toLocaleLowerCase() !== title.toLocaleLowerCase()));
      return;
    }
    if (value.length >= MAX_KNOWLEDGE_LEAVES) {
      notify.error({ title: `知识点最多选择 ${MAX_KNOWLEDGE_LEAVES} 个` });
      return;
    }
    onChange([...value, title]);
  }, [onChange, treeRoot, value]);

  return (
    <Box className={styles.shell}>
      <Box className={styles.summary}>
        <Box className={styles.chips}>
          {selectedItems.length ? selectedItems.map((item) => {
            const { trail, title } = formatPath(item.path);
            return (
              <Box key={item.title} className={styles.chip} data-in-tree={item.inTree ? "true" : "false"}>
                {trail ? <Text className={styles.chipPath} title={item.path.join(" / ")}>{trail}</Text> : null}
                <Text className={styles.chipTitle}>{title}</Text>
                <IconButton
                  size="small"
                  variant="invisible"
                  icon={XIcon}
                  aria-label={`移除知识点 ${item.title}`}
                  onClick={() => removeTitle(item.title)}
                />
              </Box>
            );
          }) : (
            <Text className={styles.empty}>尚未标注知识点</Text>
          )}
        </Box>
        <Button size="small" variant="secondary" onClick={() => setOpen(true)}>
          选择知识点
        </Button>
      </Box>
      <ErrorBanner message={loadError} title="知识树加载失败" />
      <Modal
        opened={open}
        onClose={() => setOpen(false)}
        title="选择知识点"
        centered
        size="lg"
      >
        <Box className={styles.dialog}>
          <Text className={styles.hint}>只选择知识树叶子。父级用于浏览，点选即加入本题，不能整枝勾选或新建。</Text>
          <Box className={styles.dialogTree}>
            <KnowledgeTreeView
              root={treeRoot}
              selectedLeafIds={selectedLeafIds}
              onToggle={toggleNode}
              selectionMode="leaf"
              emptyLabel="知识树中没有此项"
            />
          </Box>
          <Box className={styles.dialogFooter}>
            <Box className={styles.chips}>
              {selectedItems.length ? selectedItems.map((item) => {
                const { trail, title } = formatPath(item.path);
                return (
                  <Box key={`dialog:${item.title}`} className={styles.chip}>
                    {trail ? <Text className={styles.chipPath} title={item.path.join(" / ")}>{trail}</Text> : null}
                    <Text className={styles.chipTitle}>{title}</Text>
                    <IconButton
                      size="small"
                      variant="invisible"
                      icon={XIcon}
                      aria-label={`移除知识点 ${item.title}`}
                      onClick={() => removeTitle(item.title)}
                    />
                  </Box>
                );
              }) : <Text className={styles.empty}>尚未选择</Text>}
            </Box>
            <Button size="small" variant="primary" onClick={() => setOpen(false)}>完成</Button>
          </Box>
        </Box>
      </Modal>
    </Box>
  );
}
