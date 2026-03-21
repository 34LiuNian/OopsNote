"use client";

import { Box, Button, Spinner, Text } from "@primer/react";
import { ChevronDownIcon, ChevronRightIcon } from "@primer/octicons-react";

type SubjectTree = Record<string, Record<string, Record<string, number>>>;

type KnowledgeTreeFilterProps = {
  loading: boolean;
  subjects: string[];
  tree: SubjectTree;
  subjectFilter: string;
  gradeFilter: string;
  chapterFilter: string;
  expandedSubjects: Record<string, boolean>;
  expandedGrades: Record<string, boolean>;
  getGradesBySubject: (subject: string) => string[];
  getChaptersByGrade: (subject: string, grade: string) => string[];
  toLabel: (subject: string) => string;
  onClearAll: () => void;
  onPickSubject: (subject: string) => void;
  onPickGrade: (subject: string, grade: string) => void;
  onPickChapter: (subject: string, grade: string, chapter: string) => void;
  onToggleSubjectExpand: (subject: string, defaultExpanded: boolean) => void;
  onToggleGradeExpand: (gradeKey: string, defaultExpanded: boolean) => void;
};

export function KnowledgeTreeFilter({
  loading,
  subjects,
  tree,
  subjectFilter,
  gradeFilter,
  chapterFilter,
  expandedSubjects,
  expandedGrades,
  getGradesBySubject,
  getChaptersByGrade,
  toLabel,
  onClearAll,
  onPickSubject,
  onPickGrade,
  onPickChapter,
  onToggleSubjectExpand,
  onToggleGradeExpand,
}: KnowledgeTreeFilterProps) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Box>
          <Text sx={{ fontWeight: 600 }}>知识点目录</Text>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>先选目录，再看右边对应的标签</Text>
        </Box>
        {loading ? <Spinner size="small" /> : null}
      </Box>

      <Button
        block
        size="small"
        onClick={onClearAll}
        variant={!subjectFilter && !gradeFilter && !chapterFilter ? "primary" : "default"}
      >
        全部知识点
      </Button>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 640, overflowY: "auto" }}>
        {subjects.map((subject) => {
          const isSubjectSelected = subjectFilter === subject;
          const isSubjectExpanded = expandedSubjects[subject] ?? isSubjectSelected;
          const gradeCount = Object.keys(tree[subject] || {}).length;

          return (
            <Box key={subject} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Box sx={{ display: "grid", gridTemplateColumns: "32px 1fr", gap: 1 }}>
                <Button
                  size="small"
                  sx={{ px: 0 }}
                  onClick={() => onToggleSubjectExpand(subject, isSubjectSelected)}
                  aria-label={isSubjectExpanded ? "收起学科" : "展开学科"}
                >
                  {isSubjectExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                </Button>
                <Button
                  block
                  size="small"
                  variant={isSubjectSelected ? "primary" : "default"}
                  onClick={() => onPickSubject(subject)}
                  sx={{ justifyContent: "space-between" }}
                >
                  <span>{toLabel(subject)}</span>
                  <span>{gradeCount}</span>
                </Button>
              </Box>

              {isSubjectExpanded ? (
                <Box sx={{ pl: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                  {getGradesBySubject(subject).map((grade) => {
                    const isGradeSelected = gradeFilter === grade;
                    const gradeKey = `${subject}:${grade}`;
                    const isGradeExpanded = expandedGrades[gradeKey] ?? isGradeSelected;
                    const chapterCount = Object.keys(tree[subject]?.[grade] || {}).length;

                    return (
                      <Box key={gradeKey} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        <Box sx={{ display: "grid", gridTemplateColumns: "32px 1fr", gap: 1 }}>
                          <Button
                            size="small"
                            sx={{ px: 0 }}
                            onClick={() => onToggleGradeExpand(gradeKey, isGradeSelected)}
                            aria-label={isGradeExpanded ? "收起年级" : "展开年级"}
                          >
                            {isGradeExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                          </Button>
                          <Button
                            block
                            size="small"
                            variant={isGradeSelected ? "primary" : "default"}
                            onClick={() => onPickGrade(subject, grade)}
                            sx={{ justifyContent: "space-between" }}
                          >
                            <span>{grade}</span>
                            <span>{chapterCount}</span>
                          </Button>
                        </Box>

                        {isGradeExpanded ? (
                          <Box sx={{ pl: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                            {getChaptersByGrade(subject, grade).map((chapter) => (
                              <Button
                                key={`${subject}:${grade}:${chapter}`}
                                block
                                size="small"
                                variant={chapterFilter === chapter ? "primary" : "default"}
                                onClick={() => onPickChapter(subject, grade, chapter)}
                                sx={{ justifyContent: "space-between" }}
                              >
                                <span>{chapter}</span>
                                <span>{tree[subject]?.[grade]?.[chapter] || 0}</span>
                              </Button>
                            ))}
                          </Box>
                        ) : null}
                      </Box>
                    );
                  })}
                </Box>
              ) : null}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
