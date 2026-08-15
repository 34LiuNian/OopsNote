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
import sxStyles from "./AnnotationForm.sx.module.css";

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
        <Box className={["capture-annotation", sxStyles.sx1].filter(Boolean).join(" ")} >
            <Box className={["capture-annotation__details", sxStyles.sx2].filter(Boolean).join(" ")} >
                <FormControl>
                    <FormControl.Label>分值</FormControl.Label>
                    <Box
                        className={sxStyles.sx3}
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
                            className={sxStyles.sx4}
                        />
                        <Box
                            className={sxStyles.sx5}
                        >
                            /
                        </Box>
                        <TextInput
                            placeholder="总分"
                            value={difficultyRight}
                            onChange={(e) => onDifficultyRightChange(e.target.value)}
                            ref={difficultyRightRef}
                            className={sxStyles.sx6}
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

            <Box className={sxStyles.sx7}>
                <Button
                    size="small"
                    variant="invisible"
                    onClick={() => onShowAdvancedChange(!showAdvanced)}
                >
                    {showAdvanced ? "收起高级选项" : "展开高级选项"}
                </Button>
            </Box>

            {showAdvanced && (
                <Box className={sxStyles.sx8}>
                    <Box className={sxStyles.sx9}>
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

            <Box className={sxStyles.sx10}>
                <Button
                    variant="primary"
                    onClick={onSubmit}
                    disabled={isLoading}
                >
                    {isLoading ? <><Spinner size="small" className={sxStyles.sx11} />入队中...</> : "提交并入队"}
                </Button>
                <Button onClick={onSkip} disabled={isLoading}>
                    跳过
                </Button>
            </Box>
        </Box>
    );
}
