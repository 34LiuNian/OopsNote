"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Checkbox,
  Heading,
  Text,
  Label,
  Select,
  TextInput,
  FormControl,
  Spinner,
} from "@primer/react";
import { useTagDimensions } from "../../features/tags";
import { compilePaper, listProblems } from "../../features/tasks";
import type { ProblemSummary } from "../../types/api";

const SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
];

export default function PaperBuilderPage() {
  const [subject, setSubject] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const { effectiveDimensions: tagStyles } = useTagDimensions();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [paperTitle, setPaperTitle] = useState("2024年普通高等学校招生全国统一考试");
  const [paperSubtitle, setPaperSubtitle] = useState("数学");
  const [paperPdfUrl, setPaperPdfUrl] = useState<string | null>(null);
  const [paperError, setPaperError] = useState<{ message: string; log?: string } | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);

  const selectedItems = useMemo(
    () => items.filter((item) => selected[`${item.task_id}:${item.problem_id}`]),
    [items, selected],
  );

  const selectedCount = selectedItems.length;

  function toggleSelected(key: string, next: boolean) {
    setSelected((prev) => ({ ...prev, [key]: next }));
  }

  function clearSelected() {
    setSelected({});
  }

  async function generatePaper() {
    if (selectedCount === 0) {
      setPaperError({ message: "请先选择要加入试卷的题目。" });
      return;
    }
    setPaperError(null);
    setPaperLoading(true);
    try {
      const response = await compilePaper({
        items: selectedItems.map((item) => ({
          task_id: item.task_id,
          problem_id: item.problem_id,
        })),
        title: paperTitle.trim() || "试卷",
        subtitle: paperSubtitle.trim() || "",
      });

      if (!response.ok) {
        const contentType = response.headers.get("Content-Type") || "";
        let message = `生成失败: ${response.status}`;
        let log = "";

        if (contentType.includes("application/json")) {
          const data = (await response.json()) as { detail?: { message?: string; log?: string } | string };
          if (typeof data.detail === "string") {
            message = data.detail;
          } else if (data.detail) {
            message = data.detail.message || message;
            log = data.detail.log || "";
          }
        } else {
          const text = await response.text();
          if (text) message = text;
        }

        setPaperError({ message, log });
        return;
      }

      const blob = await response.blob();
      const nextUrl = URL.createObjectURL(blob);
      setPaperPdfUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return nextUrl;
      });
      setPaperError(null);
    } catch (err) {
      setPaperError({ message: err instanceof Error ? err.message : "生成失败，请稍后重试。" });
    } finally {
      setPaperLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError("");

      try {
        const data = await listProblems({ subject: subject || undefined, tag: tag || undefined });
        if (!cancelled) {
          setItems(data.items);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载题库失败");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [subject, tag]);

  useEffect(() => {
    return () => {
      if (paperPdfUrl) URL.revokeObjectURL(paperPdfUrl);
    };
  }, [paperPdfUrl]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 2 }}>
        <Box>
          <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Paper Builder</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>
            试卷生成器
          </Heading>
        </Box>
        <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          <Label variant="secondary">已选 {selectedCount} 道</Label>
          <Button size="small" variant="outline" onClick={clearSelected} disabled={selectedCount === 0 || paperLoading}>
            清空选择
          </Button>
          <Button size="small" variant="primary" onClick={generatePaper} disabled={selectedCount === 0 || paperLoading}>
            {paperLoading ? "生成中..." : "生成试卷"}
          </Button>
        </Box>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <FormControl>
            <FormControl.Label>试卷标题</FormControl.Label>
            <TextInput value={paperTitle} onChange={(e) => setPaperTitle(e.target.value)} block />
          </FormControl>
          <FormControl>
            <FormControl.Label>副标题</FormControl.Label>
            <TextInput value={paperSubtitle} onChange={(e) => setPaperSubtitle(e.target.value)} block />
          </FormControl>
          <Box>
            <Text sx={{ fontSize: 1, color: "fg.muted" }}>已选题目</Text>
            {selectedCount === 0 ? (
              <Text sx={{ color: "fg.muted" }}>尚未选择题目</Text>
            ) : (
              <Box sx={{ mt: 2, display: "flex", flexWrap: "wrap", gap: 1 }}>
                {selectedItems.map((item) => (
                  <Label key={`${item.task_id}:${item.problem_id}`} variant="secondary">
                    {item.question_no ? `题号 ${item.question_no}` : `题目 ${item.problem_id.slice(0, 4)}`}
                  </Label>
                ))}
              </Box>
            )}
          </Box>
        </Box>

        <Box sx={{ minHeight: 320, border: "1px solid", borderColor: "border.default", borderRadius: 2, overflow: "hidden" }}>
          {paperError ? (
            <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
              <Text sx={{ color: "danger.fg", fontWeight: "bold" }}>生成失败</Text>
              <Text sx={{ mt: 2, display: "block", color: "danger.fg", whiteSpace: "pre-wrap" }}>{paperError.message}</Text>
              {paperError.log ? (
                <Text
                  sx={{
                    mt: 3,
                    display: "block",
                    fontSize: 0,
                    whiteSpace: "pre-wrap",
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                  }}
                >
                  {paperError.log}
                </Text>
              ) : null}
            </Box>
          ) : paperPdfUrl ? (
            <iframe title="试卷 PDF 预览" src={paperPdfUrl} style={{ width: "100%", height: "100%", border: 0 }} />
          ) : (
            <Box sx={{ p: 3 }}>
              <Text sx={{ color: "fg.muted" }}>选择题目后点击“生成试卷”即可预览。</Text>
            </Box>
          )}
        </Box>
      </Box>

      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Filter</Text>
            <Heading as="h3" sx={{ fontSize: 2 }}>
              题库筛选
            </Heading>
          </Box>
          {isLoading && <Spinner size="small" />}
          {error && <Label variant="danger">{error}</Label>}
        </Box>

        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3, mb: 3 }}>
          <FormControl>
            <FormControl.Label>学科筛选</FormControl.Label>
            <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
              {SUBJECT_OPTIONS.map((option) => (
                <Select.Option key={option.value || "all"} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl>
            <FormControl.Label>知识点包含</FormControl.Label>
            <TextInput placeholder="例如：勾股定理" value={tag} onChange={(e) => setTag(e.target.value)} block />
          </FormControl>
        </Box>

        {items.length === 0 ? (
          <Box sx={{ textAlign: "center", p: 4, color: "fg.muted" }}>
            <Text as="p" sx={{ fontWeight: "bold" }}>
              暂无题目。
            </Text>
          </Box>
        ) : (
          <Box>
            <Box
              sx={{
                display: ["none", "grid"],
                gridTemplateColumns: "auto 2fr 1fr 2fr",
                gap: 2,
                px: 2,
                py: 1,
                bg: "canvas.subtle",
                fontWeight: "bold",
                fontSize: 1,
                color: "fg.muted",
              }}
            >
              <Text>选择</Text>
              <Text>题目</Text>
              <Text>学科 / 年级</Text>
              <Text>标签</Text>
            </Box>
            <Box as="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
              {items.map((item) => (
                <Box
                  as="li"
                  key={`${item.task_id}-${item.problem_id}`}
                  sx={{ px: 2, py: 2, borderBottom: "1px solid", borderColor: "border.muted" }}
                >
                  <Box
                    sx={{
                      display: ["flex", "grid"],
                      flexDirection: "column",
                      gridTemplateColumns: ["1fr", "auto 2fr 1fr 2fr"],
                      gap: 2,
                      alignItems: ["flex-start", "center"],
                    }}
                  >
                    <Box sx={{ width: "100%" }}>
                      <Checkbox
                        checked={!!selected[`${item.task_id}:${item.problem_id}`]}
                        onChange={(e) => toggleSelected(`${item.task_id}:${item.problem_id}`, e.target.checked)}
                        aria-label="选择题目"
                      />
                    </Box>
                    <Box sx={{ width: "100%" }}>
                      <Text sx={{ fontWeight: "bold", display: "block" }}>
                        {item.question_no ? `题号 ${item.question_no}` : "题目"}
                      </Text>
                      {item.source && (
                        <Text sx={{ fontSize: 0, color: "fg.muted", display: "block" }}>{item.source}</Text>
                      )}
                    </Box>
                    <Box sx={{ width: "100%", display: "flex", alignItems: "center", gap: 2 }}>
                      <Text sx={{ display: "block" }}>{item.subject}</Text>
                      {item.grade && <Label variant="secondary">{item.grade}</Label>}
                    </Box>
                    <Box sx={{ width: "100%", display: "flex", flexWrap: "wrap", gap: 1 }}>
                      {item.knowledge_points.length === 0 &&
                      !(item.knowledge_tags?.length || item.error_tags?.length || item.user_tags?.length) ? (
                        <Text sx={{ color: "fg.muted" }}>—</Text>
                      ) : (
                        <>
                          {(item.knowledge_tags || []).map((t) => (
                            <Label key={`k:${t}`} variant={(tagStyles.knowledge?.label_variant || "accent") as any}>
                              {t}
                            </Label>
                          ))}
                          {(item.error_tags || []).map((t) => (
                            <Label key={`e:${t}`} variant={(tagStyles.error?.label_variant || "danger") as any}>
                              {t}
                            </Label>
                          ))}
                          {(item.user_tags || []).map((t) => (
                            <Label key={`u:${t}`} variant={(tagStyles.custom?.label_variant || "secondary") as any}>
                              {t}
                            </Label>
                          ))}
                          {item.knowledge_points.map((kp) => (
                            <Label key={`ai:${kp}`} variant="secondary">
                              {kp}
                            </Label>
                          ))}
                        </>
                      )}
                    </Box>
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}
