"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Box, Button, Spinner, Text } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { PageHeader } from "@/components/layout/PageHeader";
import { deletePaper, listPapers } from "@/features/papers";
import { confirmAction } from "@/lib/confirm";
import { notifyRequestError } from "@/lib/requestError";
import type { PaperDraft } from "@/types/api";
import sxStyles from "./page.sx.module.css";

export default function PapersPage() {
  const router = useRouter();
  const [papers, setPapers] = useState<PaperDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void listPapers()
      .then((response) => setPapers(response.items))
      .catch((reason) => setError(notifyRequestError("加载试卷草稿失败", reason, "草稿加载失败")))
      .finally(() => setLoading(false));
  }, []);

  function removePaper(paper: PaperDraft) {
    confirmAction({
      title: "删除试卷草稿",
      message: `删除“${paper.title}”？题库中的原题不会删除。`,
      confirmLabel: "删除",
      destructive: true,
      onConfirm: async () => {
        await deletePaper(paper.id);
        setPapers((current) => current.filter((item) => item.id !== paper.id));
      },
    });
  }

  return (
    <Box className={sxStyles.sx1}>
      <PageHeader
        title="试卷草稿"
        description="草稿会自动保存并永久保留，直到你主动删除"
        action={<Button variant="primary" size="small" onClick={() => router.push("/papers/new")}>新建试卷</Button>}
      />
      {loading ? <Box className={sxStyles.sx2}><Spinner /></Box> : null}
      <ErrorBanner message={error} title="加载试卷草稿失败" />
      {!loading && !papers.length ? (
        <Box className={sxStyles.sx3}>
          <Text className={sxStyles.sx4}>还没有试卷草稿。</Text>
        </Box>
      ) : null}
      <Box className={sxStyles.sx5}>
        {papers.map((paper) => (
          <Box key={paper.id} className={sxStyles.sx6}>
            <Text className={sxStyles.sx7}>{paper.title}</Text>
            <Text className={sxStyles.sx8}>
              {paper.items.length} 道题 · 更新于 {new Date(paper.updated_at).toLocaleString()}
            </Text>
            <Box className={sxStyles.sx9}>
              <Button variant="primary" size="small" onClick={() => router.push(`/papers/${paper.id}/edit`)}>继续编辑</Button>
              <Button size="small" onClick={() => void removePaper(paper)}>删除</Button>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
