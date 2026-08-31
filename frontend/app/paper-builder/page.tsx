"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Text,
  Select,
  TextInput,
  FormControl,
  Spinner,
} from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { compilePaper, useProblemList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";
import { TagSelectorRow } from "../../components/TagSelectorRow";
import { useTagDimensions } from "../../features/tags";
import { SUBJECT_OPTIONS } from "../../config/subjects";
import { PageHeader } from "@/components/layout/PageHeader";
import { ApiError } from "@/lib/api";
import { notify } from "@/lib/notify";
import { notifyRequestError } from "@/lib/requestError";
import sxStyles from "./page.sx.module.css";

const BUILDER_SUBJECT_OPTIONS = [
  ...SUBJECT_OPTIONS,
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
  const [subject, setSubject] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [knowledgeFilter, setKnowledgeFilter] = useState<string[]>([]);
  const [errorFilter, setErrorFilter] = useState<string[]>([]);
  const [customFilter, setCustomFilter] = useState<string[]>([]);
  const [dateAfter, setDateAfter] = useState<string | null>(null);
  const [dateBefore, setDateBefore] = useState<string | null>(null);
  const { effectiveDimensions: tagStyles } = useTagDimensions();

  const { items: allItems } = useProblemList();
  const defaultDateRange = useMemo(() => {
    const dates = allItems
      .map((item) => item.created_at.slice(0, 10))
      .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value))
      .sort();
    return {
      after: dates[0] ?? "",
      before: dates[dates.length - 1] ?? "",
    };
  }, [allItems]);
  const effectiveDateAfter = dateAfter ?? defaultDateRange.after;
  const effectiveDateBefore = dateBefore ?? defaultDateRange.before;

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
    created_after: effectiveDateAfter || undefined,
    created_before: effectiveDateBefore || undefined,
  });

  useEffect(() => {
    if (!error) return;
    notifyRequestError("加载题库失败", error);
  }, [error]);

  const [selected, setSelected] = useState<Record<string, boolean>>({});

  // 根据学科获取学科标签
  const subjectLabel = useMemo(() => {
    const subj = BUILDER_SUBJECT_OPTIONS.find((opt) => opt.value === subject);
    return subj?.label || "综合";
  }, [subject]);

  // 试卷标题 - 直接使用计算后的初始值
  const [paperTitle, setPaperTitle] = useState<string>(() => generateDefaultTitle(subjectLabel));
  const [isPaperTitleCustomized, setIsPaperTitleCustomized] = useState(false);

  const handleSubjectChange = useCallback((nextSubject: string) => {
    setSubject(nextSubject);
    if (!isPaperTitleCustomized) {
      const nextLabel = BUILDER_SUBJECT_OPTIONS.find((option) => option.value === nextSubject)?.label || "综合";
      setPaperTitle(generateDefaultTitle(nextLabel));
    }
  }, [isPaperTitleCustomized]);

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
      notify.error({ title: "无法生成试卷", description: "请先选择要加入试卷的题目。" });
      return;
    }
    setPaperError(null);
    setPaperLoading(true);
    // 清空上一次生成的 PDF URL，避免在加载时显示旧试卷
    setPaperPdfUrl(null);
    try {
      const pdf = await compilePaper({
        items: selectedItems.map((item) => ({
          task_id: item.task_id,
          problem_id: item.problem_id,
        })),
        title: paperTitle.trim() || "试卷",
      });
      const nextUrl = URL.createObjectURL(pdf);
      setPaperPdfUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return nextUrl;
      });
      setPaperError(null);
    } catch (err) {
      const log = err instanceof ApiError && typeof err.payload?.details?.log === "string"
        ? err.payload.details.log
        : undefined;
      setPaperError({
        message: err instanceof Error ? err.message : "生成失败，请稍后重试。",
        log,
      });
      notify.error({
        title: "生成试卷失败",
        description: log ? `${err instanceof Error ? err.message : "生成失败，请稍后重试。"}\n${log}` : err instanceof Error ? err.message : "生成失败，请稍后重试。",
      });
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
    <Box className={sxStyles.sx1}>
      <PageHeader
        title="试题组卷"
        description="从题库选择题目，生成练习试卷"
        action={isLoading ? <Spinner size="small" /> : undefined}
      />
      <Box className={sxStyles.sx2}>
        {/* <Box> */}

        <Box className={sxStyles.sx3}>
          <Box className={sxStyles.sx4}>
            <Box className={sxStyles.sx5}>
              <ErrorBanner message={error ?? ""} title="加载题库失败" />
              <Text className={sxStyles.sx6}>已选 {selectedCount} 道</Text>
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
          <Box className={sxStyles.sx7}>
            <FormControl>
              <FormControl.Label>试卷标题</FormControl.Label>
              <TextInput
                value={paperTitle}
                onChange={(e) => {
                  setPaperTitle(e.target.value);
                  setIsPaperTitleCustomized(true);
                }}
                block
              />
            </FormControl>
            <FormControl>
              <FormControl.Label>学科</FormControl.Label>
              <Select value={subject} onValueChange={handleSubjectChange} block>
                  {BUILDER_SUBJECT_OPTIONS.map((option) => (
                  <Select.Option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </Select.Option>
                ))}
              </Select>
            </FormControl>
            <FormControl>
              <FormControl.Label>日期范围</FormControl.Label>
              <Box className={sxStyles.sx8}>
                <TextInput
                  type="date"
                  value={effectiveDateAfter}
                  onChange={(e) => setDateAfter(e.target.value)}
                  className={sxStyles.sx9}
                  placeholder="起始"
                />
                <Text className={sxStyles.sx10}>-</Text>
                <TextInput
                  type="date"
                  value={effectiveDateBefore}
                  onChange={(e) => setDateBefore(e.target.value)}
                  className={sxStyles.sx11}
                  placeholder="结束"
                />
                <Button
                  size="small"
                  onClick={() => {
                    setDateAfter('');
                    setDateBefore('');
                  }}
                  disabled={!effectiveDateAfter && !effectiveDateBefore}
                  className={sxStyles.sx12}
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

          {isLoading ? (
            <Box className={sxStyles.sx13}>
              <Spinner size="small" />
              <Text as="p" className={sxStyles.sx14}>正在加载题库…</Text>
            </Box>
          ) : items.length === 0 ? (
            <Box className={sxStyles.sx15}>
              <Text as="p" className={sxStyles.sx16}>
                暂无题目。
              </Text>
            </Box>
          ) : (
            <Box>
              <Box as="ul" className={sxStyles.sx17}>
                {items.map((item) => (
                  <Box
                    as="li"
                    key={`${item.task_id}-${item.problem_id}`}
                    className={sxStyles.sx18}
                  >
                    <ProblemListItem
                      item={item}
                      selected={!!selected[`${item.task_id}:${item.problem_id}`]}
                      toggleKey={`${item.task_id}:${item.problem_id}`}
                      onToggleSelection={toggleSelected}
                      showMetaPills
                      showAnswerPeek
                    />
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Box>
        {/* </Box> */}
        <Box className={sxStyles.sx19}>
          {paperLoading ? (
            <Box className={sxStyles.sx20}>
              <Spinner size="large" />
              <Text className={sxStyles.sx21}>正在生成试卷...</Text>
            </Box>
          ) : paperError ? (
            <Box className={sxStyles.sx22}>
              <Text className={sxStyles.sx23}>生成失败</Text>
              <Text className={sxStyles.sx24}>{paperError.message}</Text>
              {paperError.log ? (
                <Text
                  className={sxStyles.sx25}
                >
                  {paperError.log}
                </Text>
              ) : null}
            </Box>
          ) : paperPdfUrl ? (
            <iframe title="试卷 PDF 预览" src={paperPdfUrl} style={{ width: "100%", height: "100%", border: 0 }} />
          ) : (
            <Box className={sxStyles.sx26}>
              <Text className={sxStyles.sx27}>选择题目后点击“生成试卷”即可预览。</Text>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
