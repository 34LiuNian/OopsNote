"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Box, Button, Spinner, Text } from "@/components/ui/primitives";
import { PageHeader } from "@/components/layout/PageHeader";
import { deletePaper, listPapers } from "@/features/papers";
import type { PaperDraft } from "@/types/api";

export default function PapersPage() {
  const router = useRouter();
  const [papers, setPapers] = useState<PaperDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void listPapers()
      .then((response) => setPapers(response.items))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "草稿加载失败"))
      .finally(() => setLoading(false));
  }, []);

  async function removePaper(paper: PaperDraft) {
    if (!window.confirm(`删除“${paper.title}”？题库中的原题不会删除。`)) return;
    await deletePaper(paper.id);
    setPapers((current) => current.filter((item) => item.id !== paper.id));
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <PageHeader
        title="试卷草稿"
        description="草稿会自动保存并永久保留，直到你主动删除"
        action={<Button variant="primary" size="small" onClick={() => router.push("/papers/new")}>新建试卷</Button>}
      />
      {loading ? <Box sx={{ p: 5, textAlign: "center" }}><Spinner /></Box> : null}
      {error ? <Text sx={{ color: "danger.fg" }}>{error}</Text> : null}
      {!loading && !papers.length ? (
        <Box sx={{ p: 5, border: "1px dashed", borderColor: "border.default", borderRadius: 2, textAlign: "center" }}>
          <Text sx={{ color: "fg.muted" }}>还没有试卷草稿。</Text>
        </Box>
      ) : null}
      <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "repeat(2, minmax(0, 1fr))"], gap: 2 }}>
        {papers.map((paper) => (
          <Box key={paper.id} sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
            <Text sx={{ display: "block", fontWeight: 650, fontSize: 2 }}>{paper.title}</Text>
            <Text sx={{ display: "block", mt: 1, color: "fg.muted", fontSize: 1 }}>
              {paper.items.length} 道题 · 更新于 {new Date(paper.updated_at).toLocaleString()}
            </Text>
            <Box sx={{ display: "flex", gap: 2, mt: 3 }}>
              <Button variant="primary" size="small" onClick={() => router.push(`/papers/${paper.id}/edit`)}>继续编辑</Button>
              <Button size="small" onClick={() => void removePaper(paper)}>删除</Button>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
