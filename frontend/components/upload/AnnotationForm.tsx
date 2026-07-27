"use client";

import {
    Box,
    Button,
    FormControl,
    TextInput,
    Select,
    Spinner,
} from "@/components/ui/primitives";
import { TagSelectorRow } from "@/components/TagSelectorRow";
import type { TagDimensionStyle } from "@/types/api";
import { SUBJECT_OPTIONS } from "@/config/subjects";

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
    difficultyLeftRef?: React.RefObject<HTMLInputElement | null>;
    difficultyRightRef?: React.RefObject<HTMLInputElement | null>;
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
        <Box className="capture-annotation" sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box className="capture-annotation__details" sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3 }}>
                <FormControl>
                    <FormControl.Label>分值</FormControl.Label>
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            border: '1px solid',
                            borderColor: 'border.default',
                            borderRadius: 2,
                            overflow: 'hidden',
                            ':focus-within': {
                                boxShadow: '0 0 0 2px var(--borderColor-accent-emphasis)',
                            },
                        }}
                    >
                        <TextInput
                            placeholder="得分"
                            value={difficultyLeft}
                            ref={difficultyLeftRef}
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
                                    border: 'none',
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
                            placeholder="总分"
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
                    <Box sx={{ display: 'grid', gridTemplateColumns: ['1fr', '1fr 1fr'], gap: 3 }}>
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
                            <Select value={subject} onValueChange={onSubjectChange} block>
                                <Select.Option value="auto">自动识别</Select.Option>
                                  {SUBJECT_OPTIONS.map((option) => (
                                    <Select.Option key={option.value} value={option.value}>
                                      {option.label}
                                    </Select.Option>
                                  ))}
                            </Select>
                        </FormControl>
                    </Box>

                    <FormControl>
                        <FormControl.Label>题型</FormControl.Label>
                        <Select value={questionType} onValueChange={onQuestionTypeChange} block>
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
