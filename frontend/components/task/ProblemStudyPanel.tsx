"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Box, Button, IconButton, Select, Text, TextInput, Textarea } from "@/components/ui/primitives";
import { ProblemCard } from "@/components/ProblemCard";
import { fetchJson } from "@/lib/api";
import { confirmAction } from "@/lib/confirm";
import type { TaskResponse } from "@/types/api";
import sxStyles from "./ProblemStudyPanel.sx.module.css";

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

  useEffect(() => {
    if (section !== "duplicates" || mergedInto) return;

    const controller = new AbortController();
    void fetchJson<{ items: DuplicateCandidate[] }>(`/tasks/${taskId}/duplicates`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setCandidates(data.items);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        onError(error instanceof Error ? error.message : "加载疑似相同题失败");
      });

    return () => controller.abort();
  }, [mergedInto, onError, problem.problem_id, section, taskId]);

  const merge = async (candidateTaskId: string, mergeDirection: "into_current" | "into_candidate") => {
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

  const requestMerge = (candidateTaskId: string, mergeDirection: "into_current" | "into_candidate") => {
    const message = mergeDirection === "into_current"
      ? "确认将候选题并入此当前题？"
      : "确认将此当前题并入候选题？";
    confirmAction({
      title: "归并相同题",
      message,
      confirmLabel: "归并",
      destructive: true,
      onConfirm: () => merge(candidateTaskId, mergeDirection),
    });
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
      <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
        <Text className={sxStyles.sx2}>此题已并入另一题</Text>
        <Link href={`/tasks/${mergedInto.task_id}`} style={{ textDecoration: "none" }}>
          <Button size="small" variant="secondary" className={sxStyles.sx3}>跳转查看</Button>
        </Link>
      </Box>
    );
  }
  if (mergedInto) return null;
  if (section === "duplicates" && candidates.length === 0) return null;

  return (
    <Box className={sxStyles.sx4}>
      {section === "duplicates" && candidates.length > 0 && (
        <Box className={["oops-card", sxStyles.sx5].filter(Boolean).join(" ")} >
          <Box className={sxStyles.sx6}>
            <Text className={sxStyles.sx7}>疑似相同题（{candidates.length}）</Text>
            <Button size="small" variant="secondary" onClick={() => setIsExpanded((value) => !value)}>
              {isExpanded ? "收起" : "展开"}
            </Button>
          </Box>
          {isExpanded && (
            <Box className={sxStyles.sx8}>
              {candidates.map(({ task, source }) => {
                const candidate = task.problem;
                if (!candidate) return null;
                return (
                  <Box key={task.id} className={sxStyles.sx9}>
                    <Text className={sxStyles.sx10}>来源：{source || "未标注"}</Text>
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
                      diagramPlacement={candidate.diagram_placement}
                      diagramScaleAdjustmentPercent={candidate.diagram_scale_adjustment_percent}
                      diagramCanvasWidthEm={candidate.diagram_canvas_width_em}
                      diagramCanvasHeightEm={candidate.diagram_canvas_height_em}
                      diagramRenderStatus={candidate.diagram_render_status}
                      diagramError={candidate.diagram_error}
                      diagramNeedsReview={candidate.diagram_needs_review}
                      itemKeyPrefix={candidate.problem_id}
                      showTitle={false}
                      showMeta={false}
                    />
                    <Box className={sxStyles.sx11}>
                      <Button size="small" disabled={isMerging} onClick={() => requestMerge(task.id, "into_current")}>并入此当前题</Button>
                      <IconButton size="small" variant="secondary" icon={ChevronDown} aria-label="展开反向并入操作" title="展开反向并入操作" disabled={isMerging} onClick={() => setReverseOpenFor((value) => value === task.id ? "" : task.id)} />
                    </Box>
                    {reverseOpenFor === task.id && (
                      <Box className={sxStyles.sx12}>
                        <Button size="small" variant="secondary" disabled={isMerging} onClick={() => requestMerge(task.id, "into_candidate")}>并入候选题</Button>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          )}
        </Box>
      )}

      {section === "variations" && <Box>
        <Text className={sxStyles.sx13}>举一反三</Text>
        <Box className={sxStyles.sx14}>
          <Select value={direction} onValueChange={setDirection} aria-label="变式方向" block>
            <Select.Option value="change_conditions">改变条件</Select.Option>
            <Select.Option value="add_distractors">增加干扰条件</Select.Option>
            <Select.Option value="reverse_question">逆向设问</Select.Option>
            <Select.Option value="change_context">更换情境</Select.Option>
            <Select.Option value="increase_complexity">提高综合度</Select.Option>
          </Select>
          <TextInput type="number" min="1" max="5" value={count} onChange={(event) => setCount(event.currentTarget.value)} aria-label="题量" />
        </Box>
        <TextInput value={difficulty} onChange={(event) => setDifficulty(event.currentTarget.value)} placeholder="目标难度（可选）" className={sxStyles.sx15} />
        <Textarea value={customRequest} onChange={(event) => setCustomRequest(event.currentTarget.value)} placeholder="自定义要求（可选）" rows={3} maxLength={2000} className={sxStyles.sx16} />
        <Text className={sxStyles.sx17}>针对错因：{problem.error_tags?.join("、") || "未标注"}</Text>
        <Button size="small" disabled={isGenerating} onClick={() => void generate()} className={sxStyles.sx18}>
          {isGenerating ? "正在提交..." : "生成变式"}
        </Button>
        {variationTasks.length > 0 && (
          <Box className={sxStyles.sx19}>
            {variationTasks.map(({ task }) => (
              <Link key={task.id} href={`/tasks/${task.id}`} style={{ textDecoration: "none" }}>
                <Text className={sxStyles.sx20}>查看举一反三题</Text>
              </Link>
            ))}
          </Box>
        )}
      </Box>}
    </Box>
  );
}
