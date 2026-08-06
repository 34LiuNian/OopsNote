"use client";

import { Eye, FileText, Pencil, Trash2 } from "lucide-react";

import { Box, Button, IconButton, Text } from "@/components/ui/primitives";
import type { BatchSession } from "../api";
import { summarizeBatchSession } from "./batchScanSupport";

type Props = {
  sessions: BatchSession[];
  isImporting: boolean;
  onRename: (session: BatchSession) => void;
  onResume: (session: BatchSession) => void;
  onDelete: (session: BatchSession) => void;
};

export function BatchSessionHistory({ sessions, isImporting, onRename, onResume, onDelete }: Props) {
  if (!sessions.length) return null;
  return (
    <Box className="batch-scan-history">
      <Box className="batch-scan-history__header">
        <Text className="batch-scan-history__title">最近文件</Text><Text>{sessions.length}</Text>
      </Box>
      {sessions.slice(0, 8).map((session) => {
        const counts = summarizeBatchSession(session);
        return (
          <Box key={session.file_hash} className="batch-scan-history__item">
            <Box className="batch-scan-history__mark"><FileText size={17} /></Box>
            <Box className="batch-scan-history__body">
              <Text className="batch-scan-history__filename">
                {session.filename}
                {!session.source_available && <span className="batch-scan-history__missing"> · 源文件缺失，重新导入相同文件可恢复</span>}
              </Text>
              <Box className="batch-scan-history__meta">
                <span><strong>{session.page_count}</strong> 页</span>
                <span><strong>{session.column_layout?.column_count ?? 1}</strong> 栏</span>
                <span><strong>{session.segments.length}</strong> 道</span>
                <span className={counts.completed > 0 ? "is-completed" : undefined}><strong>{counts.completed}</strong> 录入</span>
                <span className={counts.processing > 0 ? "is-processing" : undefined}><strong>{counts.processing}</strong> 进行中</span>
                <span className={counts.pending > 0 ? "is-pending" : undefined}><strong>{counts.pending}</strong> 未提交</span>
                <span className={counts.failed > 0 ? "is-failed" : undefined} title="包含待复核项目"><strong>{counts.failed}</strong> 失败</span>
              </Box>
            </Box>
            <IconButton icon={Pencil} size="small" variant="invisible" aria-label="重命名最近文件" title="重命名最近文件" onClick={() => onRename(session)} />
            <IconButton className="batch-scan-history__delete" icon={Trash2} size="small" variant="invisible" aria-label="删除最近文件" title="删除最近文件" onClick={() => onDelete(session)} />
            <Button size="small" variant="default" leadingVisual={Eye} onClick={() => onResume(session)} disabled={isImporting}>查看</Button>
          </Box>
        );
      })}
    </Box>
  );
}
