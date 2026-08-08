"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useRouter } from "next/navigation";
import { Box, Button, FormControl, NativeInput, Spinner, Text, TextInput } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { DEFAULT_SUBJECT, SUBJECT_OPTIONS } from "@/config/subjects";
import { getKnowledgeTree } from "@/features/tags/api";
import { createPaper } from "@/features/papers";
import { KnowledgeTreeSelector } from "@/features/papers/KnowledgeTreeSelector";
import type { DifficultyBand, KnowledgeTreeNode } from "@/types/api";
import styles from "../paperWorkflow.module.css";

const SUBJECTS = SUBJECT_OPTIONS.filter((subject) => subject.value !== "english");

const DIFFICULTY_PRESETS: Record<string, Record<DifficultyBand, number>> = {
  easy: { easy: 80, medium: 20, hard: 0 },
  medium: { easy: 50, medium: 45, hard: 5 },
  hard: { easy: 35, medium: 40, hard: 25 },
};

const PRESET_LABELS: Record<string, string> = {
  easy: "容易",
  medium: "适中",
  hard: "困难",
};

const QUESTION_TYPES = ["单选题", "多选题", "填空题", "解答题"];

function defaultTitle(subject: string): string {
  const now = new Date();
  const label = SUBJECTS.find((item) => item.value === subject)?.label ?? "综合";
  return `${now.getMonth() + 1}月${now.getDate()}日${label}试卷`;
}

function collectLeafIds(node: KnowledgeTreeNode): string[] {
  const children = node.children.filter((child) => !child.scope || child.scope === "core");
  if (!children.length) return [node.id];
  return children.flatMap(collectLeafIds);
}

function findKnowledgeNode(node: KnowledgeTreeNode, id: string): KnowledgeTreeNode | null {
  if (node.id === id) return node;
  for (const child of node.children) {
    const match = findKnowledgeNode(child, id);
    if (match) return match;
  }
  return null;
}

function compactSelectedNodes(
  root: KnowledgeTreeNode | null,
  selectedLeafIds: Set<string>,
): KnowledgeTreeNode[] {
  if (!root) return [];

  function visit(node: KnowledgeTreeNode): KnowledgeTreeNode[] {
    const leafIds = collectLeafIds(node);
    if (leafIds.length && leafIds.every((id) => selectedLeafIds.has(id))) return [node];
    return node.children
      .filter((child) => !child.scope || child.scope === "core")
      .flatMap(visit);
  }

  return root.children
    .filter((child) => !child.scope || child.scope === "core")
    .flatMap(visit);
}

export default function NewPaperPage() {
  const router = useRouter();
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [root, setRoot] = useState<KnowledgeTreeNode | null>(null);
  const [treeError, setTreeError] = useState("");
  const [selectedLeafIds, setSelectedLeafIds] = useState<Set<string>>(new Set());
  const [difficultyPreset, setDifficultyPreset] = useState("medium");
  const [distribution, setDistribution] = useState<Record<DifficultyBand, number>>(
    DIFFICULTY_PRESETS.medium,
  );
  const [counts, setCounts] = useState<Record<string, number>>(
    Object.fromEntries(QUESTION_TYPES.map((type) => [type, 0])),
  );
  const [title, setTitle] = useState(() => defaultTitle(DEFAULT_SUBJECT));
  const [titleCustomized, setTitleCustomized] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const documentRoot = document.documentElement;
    documentRoot.dataset.oopsnotePaperCompose = "active";
    return () => {
      delete documentRoot.dataset.oopsnotePaperCompose;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void getKnowledgeTree(subject)
      .then((response) => {
        if (active) setRoot(response.subjects[subject]?.root ?? null);
      })
      .catch((reason) => {
        if (active) setTreeError(reason instanceof Error ? reason.message : "知识树加载失败");
      });
    return () => { active = false; };
  }, [subject]);

  function handleSubjectChange(nextSubject: string) {
    setSubject(nextSubject);
    setRoot(null);
    setTreeError("");
    setSelectedLeafIds(new Set());
    if (!titleCustomized) setTitle(defaultTitle(nextSubject));
  }

  const selectedItems = useMemo(
    () => compactSelectedNodes(root, selectedLeafIds),
    [root, selectedLeafIds],
  );
  const easyBoundary = distribution.easy;
  const mediumBoundary = distribution.easy + distribution.medium;

  function toggleNode(node: KnowledgeTreeNode) {
    const fullNode = root ? findKnowledgeNode(root, node.id) ?? node : node;
    const leafIds = collectLeafIds(fullNode);
    setSelectedLeafIds((current) => {
      const next = new Set(current);
      const fullySelected = leafIds.every((id) => current.has(id));
      for (const id of leafIds) {
        if (fullySelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  function choosePreset(preset: string) {
    setDifficultyPreset(preset);
    if (preset !== "custom") setDistribution(DIFFICULTY_PRESETS[preset]);
  }

  function moveDifficultyBoundary(boundary: "easy" | "hard", value: number) {
    setDifficultyPreset("custom");
    setDistribution((current) => {
      const currentMediumBoundary = current.easy + current.medium;
      if (boundary === "easy") {
        const nextEasy = Math.max(0, Math.min(currentMediumBoundary, value));
        return {
          easy: nextEasy,
          medium: currentMediumBoundary - nextEasy,
          hard: 100 - currentMediumBoundary,
        };
      }
      const nextMediumBoundary = Math.max(current.easy, Math.min(100, value));
      return {
        easy: current.easy,
        medium: nextMediumBoundary - current.easy,
        hard: 100 - nextMediumBoundary,
      };
    });
  }

  function adjustQuestionCount(questionType: string, delta: number) {
    setCounts((current) => ({
      ...current,
      [questionType]: Math.max(0, Math.min(100, current[questionType] + delta)),
    }));
  }

  async function continueToEditor(autoSelect: boolean) {
    setCreating(true);
    setError("");
    try {
      const paper = await createPaper({
        title: title.trim() || "未命名试卷",
        subject,
        knowledge_tags: selectedItems.map((node) => node.title),
        knowledge_node_ids: selectedItems.map((node) => node.id),
        difficulty_preset: difficultyPreset,
        difficulty_distribution: distribution,
        requested_counts: counts,
        auto_select: autoSelect,
      });
      router.push(`/papers/${encodeURIComponent(paper.id)}/edit`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建试卷失败");
      setCreating(false);
    }
  }

  return (
    <Box className={styles.composePage}>
      <div className={styles.builderShell}>
        <KnowledgeTreeSelector
          key={subject}
          root={root}
          subject={subject}
          subjectOptions={SUBJECTS}
          selectedLeafIds={selectedLeafIds}
          onBack={() => router.push("/papers")}
          onSubjectChange={handleSubjectChange}
          onToggle={toggleNode}
        />
        <div className={styles.configColumn}>
          <div className={styles.configBody}>
            <div className={styles.paperTitleField}>
              <FormControl>
                <FormControl.Label>试卷标题</FormControl.Label>
                <TextInput
                  value={title}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    setTitleCustomized(true);
                  }}
                  block
                />
              </FormControl>
            </div>
            <section className={styles.stepSection}>
              <div className={styles.stepTitle}>
                <span className={styles.stepNumber}>01</span>
                <span>选择知识点</span>
                <span className={styles.stepHint}>从左侧知识树选择</span>
              </div>
              <ErrorBanner message={treeError} title="加载知识树失败" />
              <div className={styles.chipList}>
                {selectedItems.length ? selectedItems.map((node) => (
                  <span className={styles.chip} key={node.id}>
                    {node.title}
                    <Button type="button" variant="invisible" onClick={() => toggleNode(node)} aria-label={`移除${node.title}`}>×</Button>
                  </span>
                )) : <span className={styles.emptySelection}>未限定知识点时，将从该学科全部题目中选择。</span>}
              </div>
            </section>

            <div className={styles.settingsGrid}>
              <section className={`${styles.stepSection} ${styles.difficultySection}`}>
                <div className={styles.stepTitle}>
                  <span className={styles.stepNumber}>02</span>
                  <span>难度设置</span>
                  <span className={styles.stepHint}>难度系数越高，题目越难</span>
                </div>
                <div className={styles.presetRow}>
                  {Object.keys(PRESET_LABELS).map((preset) => (
                    <Button
                      size="small"
                      variant={difficultyPreset === preset ? "secondary" : "invisible"}
                      key={preset}
                      onClick={() => choosePreset(preset)}
                    >
                      {PRESET_LABELS[preset]}
                    </Button>
                  ))}
                </div>
                <div className={styles.distributionGrid}>
                  {(["easy", "medium", "hard"] as DifficultyBand[]).map((band) => (
                    <div className={styles.distributionCard} data-band={band} key={band}>
                      <div className={styles.distributionCardHeader}>
                        <strong>{{ easy: "容易", medium: "适中", hard: "困难" }[band]}</strong>
                        <b>{distribution[band]}%</b>
                      </div>
                      <span>{{ easy: "0～0.5", medium: "0.5～0.8", hard: "0.8～1.0" }[band]}</span>
                    </div>
                  ))}
                </div>
                <div
                  className={styles.distributionSlider}
                  style={{
                    "--easy-boundary": `${easyBoundary}%`,
                    "--medium-boundary": `${mediumBoundary}%`,
                  } as CSSProperties}
                >
                  <div className={styles.distributionTrack} aria-hidden="true" />
                  <NativeInput
                    className={`${styles.distributionRange} ${styles.distributionRangeLower}`}
                    type="range"
                    min={0}
                    max={100}
                    value={easyBoundary}
                    onChange={(event) => moveDifficultyBoundary("easy", Number(event.target.value))}
                    aria-label="调整容易题占比"
                  />
                  <NativeInput
                    className={`${styles.distributionRange} ${styles.distributionRangeUpper}`}
                    type="range"
                    min={0}
                    max={100}
                    value={mediumBoundary}
                    onChange={(event) => moveDifficultyBoundary("hard", Number(event.target.value))}
                    aria-label="调整困难题占比"
                  />
                  <span className={`${styles.distributionHandle} ${styles.distributionHandleLower}`} aria-hidden="true" />
                  <span className={`${styles.distributionHandle} ${styles.distributionHandleUpper}`} aria-hidden="true" />
                </div>
                <div className={styles.distributionTicks} aria-hidden="true">
                  <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
                </div>
              </section>

              <section className={`${styles.stepSection} ${styles.questionSection}`}>
                <div className={styles.stepTitle}>
                  <span className={styles.stepNumber}>03</span>
                  <span>试题设置</span>
                  <span className={styles.stepHint}>设置题型数量</span>
                </div>
                <div className={styles.countGrid}>
                  {QUESTION_TYPES.map((type) => (
                    <label className={styles.countRow} key={type}>
                      <span>{type}</span>
                      <span className={styles.countStepper}>
                        <Button
                          variant="invisible"
                          type="button"
                          onClick={() => adjustQuestionCount(type, -1)}
                          disabled={counts[type] <= 0}
                          aria-label={`减少${type}`}
                        >
                          −
                        </Button>
                        <NativeInput
                          type="number"
                          min={0}
                          max={100}
                          value={counts[type]}
                          onChange={(event) => setCounts((current) => ({
                            ...current,
                            [type]: Math.max(0, Math.min(100, Number.parseInt(event.target.value, 10) || 0)),
                          }))}
                          aria-label={`${type}数量`}
                        />
                        <Button
                          variant="invisible"
                          type="button"
                          onClick={() => adjustQuestionCount(type, 1)}
                          disabled={counts[type] >= 100}
                          aria-label={`增加${type}`}
                        >
                          +
                        </Button>
                      </span>
                    </label>
                  ))}
                </div>
              </section>
            </div>
            <ErrorBanner message={error} title="创建试卷失败" />
          </div>

          <div className={styles.bottomBar}>
            <Button variant="secondary" disabled={creating} onClick={() => void continueToEditor(false)}>
              跳过，手动选题
            </Button>
            <Button variant="primary" disabled={creating} onClick={() => void continueToEditor(true)}>
              {creating ? <><Spinner size="small" /> 正在创建</> : "生成试卷草稿"}
            </Button>
          </div>
        </div>
      </div>
    </Box>
  );
}
