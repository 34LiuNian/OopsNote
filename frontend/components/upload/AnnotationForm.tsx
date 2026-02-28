"use client";

import { useRef } from "react";
import {
  Box,
  Button,
  FormControl,
  TextInput,
  Select,
  Spinner,
} from "@primer/react";
import { TagSelectorRow } from "../TagSelectorRow";
import type { TagDimensionStyle } from "../../types/api";

type AnnotationFormProps = {
  subject: string;
  questionNo: string;
  notes: string;
  difficultyLeft: string;
  difficultyRight: string;
  questionType: string;
  sourceTags: string[];
  knowledgeTags: string[];
  errorTags: string[];
  customTags: string[];
  isLoading: boolean;
  hasFile: boolean;
  showAdvanced: boolean;
  tagStyles?: Record<string, TagDimensionStyle>;
  difficultyLeftRef?: React.RefObject<HTMLInputElement>;
  difficultyRightRef?: React.RefObject<HTMLInputElement>;
  onSubjectChange: (value: string) => void;
  onQuestionNoChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onDifficultyLeftChange: (value: string) => void;
  onDifficultyRightChange: (value: string) => void;
  onQuestionTypeChange: (value: string) => void;
  onSourceTagsChange: (value: string[]) => void;
  onKnowledgeTagsChange: (value: string[]) => void;
  onErrorTagsChange: (value: string[]) => void;
  onCustomTagsChange: (value: string[]) => void;
  onShowAdvancedChange: (value: boolean) => void;
  onSubmit: () => void;
  onSkip: () => void;
};

const DEFAULT_SUBJECT = "math";

export function AnnotationForm({
  subject,
  questionNo,
  notes,
  difficultyLeft,
  difficultyRight,
  questionType,
  sourceTags,
  knowledgeTags,
  errorTags,
  customTags,
  isLoading,
  hasFile,
  showAdvanced,
  tagStyles,
  difficultyLeftRef,
  difficultyRightRef,
  onSubjectChange,
  onQuestionNoChange,
  onNotesChange,
  onDifficultyLeftChange,
  onDifficultyRightChange,
  onQuestionTypeChange,
  onSourceTagsChange,
  onKnowledgeTagsChange,
  onErrorTagsChange,
  onCustomTagsChange,
  onShowAdvancedChange,
  onSubmit,
  onSkip,
}: AnnotationFormProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
        <FormControl>
          <FormControl.Label>难度</FormControl.Label>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid',
              borderColor: 'border.default',
              borderRadius: 2,
              overflow: 'hidden',
              ':focus-within': {
                borderColor: 'accent.fg',
                boxShadow: '0 0 0 3px color-mix(in srgb, accent.fg 20%, transparent)',
              },
            }}
          >
            <TextInput
              placeholder="题号"
              value={difficultyLeft}
              onChange={(e) => {
                const next = e.target.value;
                if (next.includes("/")) {
                  const [left, right] = next.split("/");
                  onDifficultyLeftChange(left.trim());
                  onDifficultyRightChange(right.trim());
                  difficultyRightRef?.current?.focus();
                  return;
                }
                onDifficultyLeftChange(next);
              }}
              onKeyDown={(e) => {
                if (e.key === "/") {
                  e.preventDefault();
                  difficultyRightRef?.current?.focus();
                }
              }}
              sx={{
                flex: 1,
                border: 'none',
                borderRadius: 0,
                input: {
                  textAlign: 'center',
                },
                ':focus': {
                  boxShadow: 'none',
                },
              }}
            />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                px: 2,
                color: 'fg.muted',
                userSelect: 'none',
              }}
            >
              /
            </Box>
            <TextInput
              placeholder="总题数"
              value={difficultyRight}
              onChange={(e) => onDifficultyRightChange(e.target.value)}
              ref={difficultyRightRef}
              sx={{
                flex: 1,
                border: '0px solid',
                borderRadius: 0,
                input: {
                  textAlign: 'center',
                  outline: 'none',
                },
                ':focus': {
                  boxShadow: 'none',
                },
              }}
            />
          </Box>
        </FormControl>
        <FormControl>
          <FormControl.Label>备注</FormControl.Label>
          <TextInput
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
            block
          />
        </FormControl>
      </Box>

      <TagSelectorRow
        sourceValue={sourceTags}
        onSourceChange={onSourceTagsChange}
        knowledgeValue={knowledgeTags}
        onKnowledgeChange={onKnowledgeTagsChange}
        errorValue={errorTags}
        onErrorChange={onErrorTagsChange}
        customValue={customTags}
        onCustomChange={onCustomTagsChange}
        styles={tagStyles}
      />

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
        <Button
          size="small"
          variant="invisible"
          onClick={() => onShowAdvancedChange(!showAdvanced)}
        >
          {showAdvanced ? "收起高级选项" : "展开高级选项"}
        </Button>
      </Box>

      {showAdvanced && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
            <FormControl>
              <FormControl.Label>题号</FormControl.Label>
              <TextInput
                value={questionNo}
                onChange={(e) => onQuestionNoChange(e.target.value)}
                block
              />
            </FormControl>
            <FormControl>
              <FormControl.Label>学科</FormControl.Label>
              <Select value={subject} onChange={(e) => onSubjectChange(e.target.value)} block>
                <Select.Option value="math">数学</Select.Option>
                <Select.Option value="physics">物理</Select.Option>
                <Select.Option value="chemistry">化学</Select.Option>
              </Select>
            </FormControl>
          </Box>

          <FormControl>
            <FormControl.Label>题型</FormControl.Label>
            <Select value={questionType} onChange={(e) => onQuestionTypeChange(e.target.value)} block>
              <Select.Option value="">自动识别</Select.Option>
              <Select.Option value="选择题">选择题</Select.Option>
              <Select.Option value="多选题">多选题</Select.Option>
              <Select.Option value="填空题">填空题</Select.Option>
              <Select.Option value="解答题">解答题</Select.Option>
              <Select.Option value="其它">其它</Select.Option>
            </Select>
          </FormControl>
        </Box>
      )}

      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        <Button
          variant="primary"
          onClick={onSubmit}
          disabled={isLoading}
        >
          {isLoading ? <><Spinner size="small" sx={{ mr: 1 }} />入队中...</> : "提交并入队"}
        </Button>
        <Button onClick={onSkip} disabled={isLoading}>
          跳过
        </Button>
      </Box>
    </Box>
  );
}
