"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import {
  Box,
  Heading,
  Text,
  Label,
  Select,
  TextInput,
  FormControl,
  Spinner,
  Flash,
} from "@primer/react";
import { useActiveTaskList, useProblemList } from "../../features/tasks";
import { ProblemListItem } from "../../components/ProblemListItem";

const SUBJECT_OPTIONS = [
  { value: "", label: "全部学科" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
];

export default function LibraryPage() {
  const [subject, setSubject] = useState<string>("");
  const [tag, setTag] = useState<string>("");
  const {
    items,
    isLoading,
    error,
  } = useProblemList({ subject: subject || undefined, tag: tag || undefined });
  const {
    items: activeTasks,
    activeItems: activeTaskItems,
    isLoading: isLoadingActive,
  } = useActiveTaskList({ active_only: true, subject: subject || undefined });
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});


  const toggleSelected = useCallback((key: string) => {
    setSelectedIds((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Active Tasks */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Tasks</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>进行中的任务</Heading>
          </Box>
          {isLoadingActive ? (
            <Label variant="secondary">刷新中...</Label>
          ) : activeTaskItems.length > 0 ? (
            <Label variant="secondary">进行中 {activeTaskItems.length} 条</Label>
          ) : (
            <Label variant="secondary">暂无进行中任务</Label>
          )}
        </Box>

        {activeTaskItems.length === 0 ? (
          <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
            <Text as="p" sx={{ fontWeight: 'bold' }}>当前没有进行中的任务。</Text>
            <Text as="p" sx={{ fontSize: 1 }}>上传后任务会出现在这里，可点击进入查看进度。</Text>
          </Box>
        ) : (
          <Box>
            <Box sx={{ display: ['none', 'grid'], gridTemplateColumns: '2fr 1fr 2fr', gap: 2, px: 2, py: 1, bg: 'canvas.subtle', fontWeight: 'bold', fontSize: 1, color: 'fg.muted' }}>
              <Text>任务</Text>
              <Text>学科 / 状态</Text>
              <Text>进度</Text>
            </Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {activeTaskItems.map((t) => (
                <Box as="li" key={t.id} sx={{ borderBottom: '1px solid', borderColor: 'border.muted' }}>
                  <Link href={`/tasks/${t.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <Box
                      sx={{
                        display: ['flex', 'grid'],
                        flexDirection: 'column',
                        gridTemplateColumns: '2fr 1fr 2fr',
                        gap: 2,
                        px: 2,
                        py: 2,
                        alignItems: ['flex-start', 'center'],
                        cursor: 'pointer',
                        borderRadius: 2,
                        '&:hover': { bg: 'canvas.subtle' },
                      }}
                    >
                      <Box sx={{ width: '100%' }}>
                        <Text sx={{ fontWeight: 'bold', display: 'block' }}>{t.question_no ? `题号 ${t.question_no}` : "任务"}</Text>
                        <Text sx={{ fontSize: 0, color: 'fg.muted' }}>{t.id.slice(0, 6)}</Text>
                      </Box>
                      <Box sx={{ width: '100%', display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Text sx={{ display: 'block' }}>{t.subject}</Text>
                        <Label variant="secondary">{t.status}</Label>
                      </Box>
                      <Box sx={{ width: '100%' }}>
                        <Text sx={{ fontSize: 1, color: 'fg.muted' }}>{t.stage_message || t.stage || "—"}</Text>
                      </Box>
                    </Box>
                  </Link>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>

      {/* Library Filter */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Library</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>题库总览</Heading>
          </Box>
          {isLoading && <Spinner size="small" />}
          {error && <Flash variant="danger">{error}</Flash>}
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3, mb: 3 }}>
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
            <TextInput 
              placeholder="例如：勾股定理" 
              value={tag} 
              onChange={(e) => setTag(e.target.value)} 
              block
            />
          </FormControl>
        </Box>

        <Text as="p" sx={{ fontSize: 1, color: 'fg.muted' }}>
          这里汇总了所有已解析题目，支持按学科与知识点初步筛选。
        </Text>
      </Box>

      {/* Results */}
      <Box sx={{ p: 3, border: '1px solid', borderColor: 'border.default', borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Text sx={{ fontSize: 0, color: 'fg.muted', textTransform: 'uppercase' }}>Results</Text>
            <Heading as="h2" sx={{ fontSize: 3 }}>当前筛选结果</Heading>
          </Box>
          <Label variant="secondary">共 {items.length} 道题</Label>
        </Box>

        {items.length === 0 ? (
          <Box sx={{ textAlign: 'center', p: 4, color: 'fg.muted' }}>
            <Text as="p" sx={{ fontWeight: 'bold' }}>暂无题目。</Text>
            <Text as="p" sx={{ fontSize: 1 }}>可以先在首页上传一张手稿图片，生成几道题后再回到这里查看。</Text>
          </Box>
        ) : (
          <Box>
            <Box as="ul" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {items.map((item) => (
                <Box
                  as="li"
                  key={`${item.task_id}-${item.problem_id}`}
                  sx={{
                    px: 2,
                    py: 2,
                    borderBottom: '1px solid',
                    borderColor: 'border.muted',
                  }}
                >
                  <ProblemListItem
                    item={item}
                    selected={!!selectedIds[`${item.task_id}:${item.problem_id}`]}
                    toggleKey={`${item.task_id}:${item.problem_id}`}
                    onToggleSelection={toggleSelected}
                    showCheckbox
                    showViewLink
                  />
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}
