"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Box, Button, Select, Text, TextInput, Textarea } from "@/components/ui/primitives";
import { ProblemCard } from "@/components/ProblemCard";
import { fetchJson } from "@/lib/api";
import type { TaskResponse } from "@/types/api";

type DuplicateCandidate = { task: TaskResponse["task"]; source: string };
type VariationTask = { task: TaskResponse["task"] };

type Props = {
  taskId: string;
  problem: NonNullable<TaskResponse["task"]["problem"]>;
  mergedInto?: TaskResponse["task"]["merged_into"];
  onStatusMessage: (message: string) => void;
  onError: (message: string) => void;
  onRefresh: () => Promise<void>;
  section: "duplicates" | "variations";
};

export function ProblemStudyPanel({ taskId, problem, mergedInto, onStatusMessage, onError, onRefresh, section }: Props) {
  const [candidates, setCandidates] = useState<DuplicateCandidate[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [reverseOpenFor, setReverseOpenFor] = useState<string>("");
  const [isMerging, setIsMerging] = useState(false);
  const [direction, setDirection] = useState("change_conditions");
  const [customRequest, setCustomRequest] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [count, setCount] = useState("1");
  const [isGenerating, setIsGenerating] = useState(false);
  const [variationTasks, setVariationTasks] = useState<VariationTask[]>([]);

  const loadCandidates = useCallback(async () => {
    if (mergedInto) return;
    try {
      const data = await fetchJson<{ items: DuplicateCandidate[] }>(`/tasks/${taskId}/duplicates`);
      setCandidates(data.items);
    } catch (error) {
      onError(error instanceof Error ? error.message : "加载疑似相同题失败");
    }
  }, [mergedInto, onError, taskId]);

  useEffect(() => {
    if (section === "duplicates") void loadCandidates();
  }, [loadCandidates, problem.problem_id, section]);

  const merge = async (candidateTaskId: string, mergeDirection: "into_current" | "into_candidate") => {
    const message = mergeDirection === "into_current"
      ? "确认将候选题并入此当前题？"
      : "确认将此当前题并入候选题？";
    if (!window.confirm(message)) return;
    setIsMerging(true);
    try {
      await fetchJson(`/tasks/${taskId}/duplicates/${candidateTaskId}/merge`, {
        method: "POST",
        body: JSON.stringify({ direction: mergeDirection }),
      });
      setCandidates([]);
      setIsExpanded(false);
      await onRefresh();
      onStatusMessage("相同题已归并");
    } catch (error) {
      onError(error instanceof Error ? error.message : "归并相同题失败");
    } finally {
      setIsMerging(false);
      setReverseOpenFor("");
    }
  };

  const generate = async () => {
    setIsGenerating(true);
    try {
      const data = await fetchJson<{ items: VariationTask[] }>(`/tasks/${taskId}/variations`, {
        method: "POST",
        body: JSON.stringify({
          direction,
          custom_request: customRequest,
          difficulty: difficulty || null,
          count: Number(count) || 1,
        }),
      });
      setVariationTasks(data.items);
      onStatusMessage(`已提交 ${data.items.length} 道举一反三题`);
    } catch (error) {
      onError(error instanceof Error ? error.message : "提交举一反三任务失败");
    } finally {
      setIsGenerating(false);
    }
  };

  if (mergedInto && section === "duplicates") {
    return (
      <Box className="oops-card" sx={{ p: 3 }}>
        <Text sx={{ fontWeight: 600 }}>此题已并入另一题</Text>
        <Link href={`/tasks/${mergedInto.task_id}`} style={{ textDecoration: "none" }}>
          <Button size="small" variant="secondary" sx={{ mt: 2 }}>跳转查看</Button>
        </Link>
      </Box>
    );
  }
  if (mergedInto) return null;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {section === "duplicates" && candidates.length > 0 && (
        <Box className="oops-card" sx={{ p: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
            <Text sx={{ fontWeight: 600 }}>疑似相同题（{candidates.length}）</Text>
            <Button size="small" variant="secondary" onClick={() => setIsExpanded((value) => !value)}>
              {isExpanded ? "收起" : "展开"}
            </Button>
          </Box>
          {isExpanded && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 3, mt: 3 }}>
              {candidates.map(({ task, source }) => {
                const candidate = task.problem;
                if (!candidate) return null;
                return (
                  <Box key={task.id} sx={{ borderTop: "1px solid var(--borderColor-muted)", pt: 3 }}>
                    <Text sx={{ color: "fg.muted", fontSize: 1, mb: 2 }}>来源：{source || "未标注"}</Text>
                    <ProblemCard
                      problemText={candidate.problem_text}
                      contentFormat={candidate.content_format}
                      options={candidate.options}
                      questionType={candidate.question_type}
                      diagramDetected={candidate.diagram_detected}
                      diagramKind={candidate.diagram_kind}
                      diagramTikzSource={candidate.diagram_tikz_source}
                      diagramSvg={candidate.diagram_svg}
                      diagramImagePath={candidate.diagram_image_path}
                      diagramImageTone={candidate.diagram_image_tone}
                      diagramPosition={candidate.diagram_position}
                      diagramScalePercent={candidate.diagram_scale_percent}
                      diagramRenderStatus={candidate.diagram_render_status}
                      diagramError={candidate.diagram_error}
                      diagramNeedsReview={candidate.diagram_needs_review}
                      itemKeyPrefix={candidate.problem_id}
                      showTitle={false}
                      showMeta={false}
                    />
                    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, mt: 3 }}>
                      <Button size="small" disabled={isMerging} onClick={() => void merge(task.id, "into_current")}>并入此当前题</Button>
                      <Button size="small" variant="secondary" aria-label="展开反向并入操作" title="展开反向并入操作" disabled={isMerging} onClick={() => setReverseOpenFor((value) => value === task.id ? "" : task.id)}><ChevronDown size={15} /></Button>
                    </Box>
                    {reverseOpenFor === task.id && (
                      <Box sx={{ mt: 2 }}>
                        <Button size="small" variant="secondary" disabled={isMerging} onClick={() => void merge(task.id, "into_candidate")}>并入候选题</Button>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          )}
        </Box>
      )}

      {section === "variations" && <Box className="oops-card" sx={{ p: 3 }}>
        <Text sx={{ fontWeight: 600, mb: 3 }}>举一反三</Text>
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 2 }}>
          <Select value={direction} onValueChange={setDirection} aria-label="变式方向" block>
            <Select.Option value="change_conditions">改变条件</Select.Option>
            <Select.Option value="add_distractors">增加干扰条件</Select.Option>
            <Select.Option value="reverse_question">逆向设问</Select.Option>
            <Select.Option value="change_context">更换情境</Select.Option>
            <Select.Option value="increase_complexity">提高综合度</Select.Option>
          </Select>
          <TextInput type="number" min="1" max="5" value={count} onChange={(event) => setCount(event.currentTarget.value)} aria-label="题量" />
        </Box>
        <TextInput value={difficulty} onChange={(event) => setDifficulty(event.currentTarget.value)} placeholder="目标难度（可选）" sx={{ mt: 2 }} />
        <Textarea value={customRequest} onChange={(event) => setCustomRequest(event.currentTarget.value)} placeholder="自定义要求（可选）" rows={3} maxLength={2000} sx={{ mt: 2 }} />
        <Text sx={{ fontSize: 0, color: "fg.muted", mt: 2 }}>针对错因：{problem.error_tags?.join("、") || "未标注"}</Text>
        <Button size="small" disabled={isGenerating} onClick={() => void generate()} sx={{ mt: 3 }}>
          {isGenerating ? "正在提交..." : "生成变式"}
        </Button>
        {variationTasks.length > 0 && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 3 }}>
            {variationTasks.map(({ task }) => (
              <Link key={task.id} href={`/tasks/${task.id}`} style={{ textDecoration: "none" }}>
                <Text sx={{ color: "accent.fg" }}>查看举一反三题</Text>
              </Link>
            ))}
          </Box>
        )}
      </Box>}
    </Box>
  );
}
