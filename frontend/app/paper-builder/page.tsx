"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Heading,
  Text,
  Label,
  Select,
  TextInput,
  FormControl,
  Spinner,
} from "@primer/react";
import { compilePaper, useProblemList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TagSelectorRow } from "../../components/TagSelectorRow";
import { useTagDimensions } from "../../features/tags";

const SUBJECT_OPTIONS = [
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
  { value: "", label: "全部学科" },
];

// 生成默认试卷标题：{月} 月{日} 日{学科} 作业
function generateDefaultTitle(subjectLabel: string): string {
  const now = new Date();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  return `${month}月${day}日${subjectLabel}作业`;
}

export default function PaperBuilderPage() {
  const [subject, setSubject] = useState<string>("math");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [knowledgeFilter, setKnowledgeFilter] = useState<string[]>([]);
  const [errorFilter, setErrorFilter] = useState<string[]>([]);
  const [customFilter, setCustomFilter] = useState<string[]>([]);
  const [dateAfter, setDateAfter] = useState<string>("");
  const [dateBefore, setDateBefore] = useState<string>("");
  const { effectiveDimensions: tagStyles } = useTagDimensions();

  const {
    items,
    isLoading,
    error,
  } = useProblemList({
    subject: subject || undefined,
    source: sourceFilter.length > 0 ? sourceFilter : undefined,
    knowledge_tag: knowledgeFilter.length > 0 ? knowledgeFilter : undefined,
    error_tag: errorFilter.length > 0 ? errorFilter : undefined,
    user_tag: customFilter.length > 0 ? customFilter : undefined,
    created_after: dateAfter || undefined,
    created_before: dateBefore || undefined,
  });

  const [selected, setSelected] = useState<Record<string, boolean>>({});

  // 根据学科获取学科标签
  const subjectLabel = useMemo(() => {
    const subj = SUBJECT_OPTIONS.find((opt) => opt.value === subject);
    return subj?.label || "综合";
  }, [subject]);

  // 试卷标题 - 直接使用计算后的初始值
  const [paperTitle, setPaperTitle] = useState<string>(() => generateDefaultTitle(subjectLabel));

  // 当学科改变时更新标题
  useEffect(() => {
    setPaperTitle(generateDefaultTitle(subjectLabel));
  }, [subjectLabel]);

  const [paperPdfUrl, setPaperPdfUrl] = useState<string | null>(null);
  const [paperError, setPaperError] = useState<{ message: string; log?: string } | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);

  const selectedItems = useMemo(
    () => items.filter((item) => selected[`${item.task_id}:${item.problem_id}`]),
    [items, selected],
  );

  const selectedCount = selectedItems.length;

  const toggleSelected = useCallback((key: string) => {
    setSelected((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

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
      });

      if (!response.ok) {
        const contentType = response.headers.get("Content-Type") || "";
        let message = `生成失败：${response.status}`;
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
    return () => {
      if (paperPdfUrl) URL.revokeObjectURL(paperPdfUrl);
    };
  }, [paperPdfUrl]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
        {/* <Box> */}

        <Box sx={{ borderColor: "border.default", borderRadius: 2 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 2, mb: 3 }}>
            <Box>
              <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Paper Builder</Text>
              <Heading as="h2" sx={{ fontSize: 3 }}>
                试题组卷
              </Heading>
            </Box>
            <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
              {isLoading && <Spinner size="small" />}
              {error && <Label variant="danger">{error}</Label>}
              <Text sx={{ color: "fg.muted" }}>已选 {selectedCount} 道</Text>
              <Button 
                size="small" 
                onClick={() => setSelected({})}
                disabled={selectedCount === 0}
              >
                取消全选
              </Button>
              <Button 
                size="small" 
                onClick={() => {
                  const allSelected: Record<string, boolean> = {};
                  items.forEach((item) => {
                    allSelected[`${item.task_id}:${item.problem_id}`] = true;
                  });
                  setSelected(allSelected);
                }}
                disabled={items.length === 0}
              >
                全选
              </Button>
              <Button size="small" variant="primary" onClick={generatePaper} disabled={selectedCount === 0 || paperLoading}>
                {paperLoading ? "生成中..." : "生成试卷"}
              </Button>
            </Box>
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr 1fr'], gap: 3, mb: 3 }}>
            <FormControl>
              <FormControl.Label>试卷标题</FormControl.Label>
              <TextInput value={paperTitle} onChange={(e) => setPaperTitle(e.target.value)} block />
            </FormControl>
            <FormControl>
              <FormControl.Label>学科</FormControl.Label>
              <Select value={subject} onChange={(e) => setSubject(e.target.value)} block>
                {SUBJECT_OPTIONS.map((option) => (
                  <Select.Option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </Select.Option>
                ))}
              </Select>
            </FormControl>
            <FormControl>
              <FormControl.Label>日期范围</FormControl.Label>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <TextInput
                  type="date"
                  value={dateAfter}
                  onChange={(e) => setDateAfter(e.target.value)}
                  sx={{ flex: 1, fontSize: 0 }}
                  placeholder="起始"
                />
                <Text sx={{ color: 'fg.muted', fontSize: 1 }}>-</Text>
                <TextInput
                  type="date"
                  value={dateBefore}
                  onChange={(e) => setDateBefore(e.target.value)}
                  sx={{ flex: 1, fontSize: 0 }}
                  placeholder="结束"
                />
                <Button
                  size="small"
                  onClick={() => {
                    setDateAfter('');
                    setDateBefore('');
                  }}
                  disabled={!dateAfter && !dateBefore}
                  sx={{ fontSize: 0, px: 1, py: 0 }}
                >
                  清空
                </Button>
              </Box>
            </FormControl>
          </Box>
          <TagSelectorRow
            sourceValue={sourceFilter}
            onSourceChange={setSourceFilter}
            knowledgeValue={knowledgeFilter}
            onKnowledgeChange={setKnowledgeFilter}
            errorValue={errorFilter}
            onErrorChange={setErrorFilter}
            customValue={customFilter}
            onCustomChange={setCustomFilter}
            styles={tagStyles}
            // placeholders={{
            //   knowledge: "输入知识点关键词进行筛选",
            //   error: "输入错因关键词进行筛选",
            //   custom: "输入自定义标签进行筛选",
            // }}
          />

          {items.length === 0 ? (
            <Box sx={{ textAlign: "center", p: 4, color: "fg.muted" }}>
              <Text as="p" sx={{ fontWeight: "bold" }}>
                暂无题目。
              </Text>
            </Box>
          ) : (
            <Box>
              <Box as="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
                {items.map((item) => (
                  <Box
                    as="li"
                    key={`${item.task_id}-${item.problem_id}`}
                    sx={{ px: 2, py: 2, borderBottom: "1px solid", borderColor: "border.muted" }}
                  >
                    <ProblemListItem
                      item={item}
                      selected={!!selected[`${item.task_id}:${item.problem_id}`]}
                      toggleKey={`${item.task_id}:${item.problem_id}`}
                      onToggleSelection={toggleSelected}
                    />
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Box>
        {/* </Box> */}
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
    </Box>
  );
}
