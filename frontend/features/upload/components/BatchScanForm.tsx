"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Box, Button, IconButton, Select, Spinner, Text, Textarea } from "@/components/ui/primitives";
import { BatchSegmenter, type SegmentedImage } from "@/components/upload/BatchSegmenter";
import { PageHeader } from "@/components/layout/PageHeader";
import { ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon, ContrastIcon, FileTextIcon, UploadIcon } from "@/components/ui/icons";
import { SUBJECT_OPTIONS } from "@/config/subjects";
import { notify } from "@/lib/notify";
import {
  createUploadTask,
  getBatchSession,
  listBatchSessions,
  type BatchSession,
  type BatchSessionSegment,
  processTaskInBackground,
  updateBatchSession,
  uploadBatchSource,
} from "../api";

type PdfPageHandle = {
  getViewport: (options: { scale: number }) => { width: number; height: number };
  render: (options: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => { promise: Promise<unknown> };
};

type PdfDocumentHandle = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageHandle>;
  destroy?: () => Promise<void>;
};

type PdfDocumentResource = {
  document: PdfDocumentHandle;
  url: string;
};

type ScanPage = {
  id: string;
  label: string;
  sourceName: string;
  pageNumber?: number;
  image?: File;
  pdf?: { documentId: string; pageNumber: number };
};

const PDF_IMAGE_CACHE_SIZE = 6;
const PREFETCH_PAGE_COUNT = 2;
const PRIMARY_RENDER_DELAY_MS = 80;
const PREFETCH_DELAY_MS = 500;

function isPdf(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function isPdfRenderCancellation(reason: unknown) {
  return typeof reason === "object"
    && reason !== null
    && "name" in reason
    && (reason as { name?: string }).name === "RenderingCancelledException";
}

async function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = reader.result;
      if (typeof value !== "string") {
        reject(new Error("无法读取裁剪图片"));
        return;
      }
      resolve(value.split(",").pop() || "");
    };
    reader.onerror = () => reject(reader.error || new Error("无法读取裁剪图片"));
    reader.readAsDataURL(blob);
  });
}

async function hashFile(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

async function cropSegment(file: File, segment: SegmentedImage): Promise<Blob> {
  if (segment.blob) return segment.blob;
  const source = await createImageBitmap(file);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(source.width * segment.rect.width));
    canvas.height = Math.max(1, Math.round(source.height * segment.rect.height));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("无法创建裁剪画布");
    context.drawImage(
      source,
      Math.round(source.width * segment.rect.x),
      Math.round(source.height * segment.rect.y),
      canvas.width,
      canvas.height,
      0,
      0,
      canvas.width,
      canvas.height,
    );
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("无法导出裁剪图片")), "image/png");
    });
  } finally {
    source.close();
  }
}

async function openPdf(file: File): Promise<PdfDocumentResource> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
  const url = URL.createObjectURL(file);
  try {
    const document = await pdfjs.getDocument({ url }).promise;
    return { document: document as unknown as PdfDocumentHandle, url };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

async function renderPdfPage(pdfDocument: PdfDocumentHandle, pageNumber: number, filename: string): Promise<File> {
  const page = await pdfDocument.getPage(pageNumber);
  const viewport = page.getViewport({ scale: 1.5 });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("无法创建 PDF 页面画布");
  await page.render({ canvasContext: context, viewport }).promise;
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((value) => value ? resolve(value) : reject(new Error("无法渲染 PDF 页面")), "image/png");
  });
  return new File([blob], filename, { type: "image/png" });
}

export function BatchScanForm() {
  const searchParams = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);
  const pdfDocumentsRef = useRef(new Map<string, PdfDocumentResource>());
  const imageCacheRef = useRef(new Map<string, File>());
  const renderPromisesRef = useRef(new Map<string, Promise<File>>());
  const sourceUploadRef = useRef<Promise<BatchSession> | null>(null);
  const restoredQuerySessionRef = useRef(false);
  const [pages, setPages] = useState<ScanPage[]>([]);
  const [activePageIndex, setActivePageIndex] = useState(0);
  const [pageInput, setPageInput] = useState("1");
  const [segmentsByPage, setSegmentsByPage] = useState<Record<string, SegmentedImage[]>>({});
  const [, setImageCacheVersion] = useState(0);
  const [renderingPageId, setRenderingPageId] = useState("");
  const [subject, setSubject] = useState("auto");
  const [notes, setNotes] = useState("");
  const [isImporting, setIsImporting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingSource, setIsSavingSource] = useState(false);
  const [isSystemDark, setIsSystemDark] = useState(false);
  const [isInverted, setIsInverted] = useState(false);
  const [error, setError] = useState("");
  const [isWideViewport, setIsWideViewport] = useState(false);
  const [savedSessions, setSavedSessions] = useState<BatchSession[]>([]);
  const [currentSession, setCurrentSession] = useState<BatchSession | null>(null);

  const clearPdfState = useCallback(() => {
    for (const resource of pdfDocumentsRef.current.values()) {
      const destroy = resource.document.destroy?.();
      if (destroy) void destroy.catch(() => undefined);
      URL.revokeObjectURL(resource.url);
    }
    pdfDocumentsRef.current.clear();
    imageCacheRef.current.clear();
    renderPromisesRef.current.clear();
  }, []);

  useEffect(() => () => clearPdfState(), [clearPdfState]);

  const refreshSavedSessions = useCallback(() => {
    return listBatchSessions().then(setSavedSessions).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshSavedSessions();
  }, [refreshSavedSessions]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1180px)");
    const update = () => setIsWideViewport(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => {
      setIsSystemDark(media.matches);
      if (!media.matches) setIsInverted(false);
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (pages.length === 0) {
      delete document.documentElement.dataset.oopsnoteBatchScan;
      return;
    }
    document.documentElement.dataset.oopsnoteBatchScan = "active";
    return () => {
      delete document.documentElement.dataset.oopsnoteBatchScan;
    };
  }, [pages.length]);

  const activePage = pages[activePageIndex] ?? null;

  useEffect(() => {
    setPageInput(String(activePageIndex + 1));
  }, [activePageIndex]);

  const goToPage = useCallback((requestedPage: number) => {
    if (pages.length === 0 || !Number.isFinite(requestedPage)) return;
    const pageIndex = Math.max(0, Math.min(pages.length - 1, Math.floor(requestedPage) - 1));
    setActivePageIndex(pageIndex);
    setPageInput(String(pageIndex + 1));
  }, [pages.length]);

  const commitPageInput = useCallback(() => {
    goToPage(Number(pageInput));
  }, [goToPage, pageInput]);

  const visiblePages = useMemo(() => {
    if (!activePage) return [];
    const nextPage = isWideViewport ? pages[activePageIndex + 1] : null;
    return nextPage ? [activePage, nextPage] : [activePage];
  }, [activePage, activePageIndex, isWideViewport, pages]);
  const allSegments = useMemo(
    () => pages.flatMap((page) => segmentsByPage[page.id] ?? []),
    [pages, segmentsByPage],
  );
  const persistedSegments = useMemo<BatchSessionSegment[]>(() => {
    let nextQuestionNo = 1;
    return pages.flatMap((page, pageIndex) => (segmentsByPage[page.id] ?? []).map((segment) => {
      const questionNo = segment.questionNo ?? nextQuestionNo;
      nextQuestionNo = Math.max(nextQuestionNo, questionNo + 1);
      return {
        id: segment.id,
        page_index: pageIndex,
        x: segment.rect.x,
        y: segment.rect.y,
        width: segment.rect.width,
        height: segment.rect.height,
        question_no: questionNo,
        status: segment.status ?? "pending",
        task_id: segment.taskId,
        problem_ids: segment.problemIds ?? [],
        error: segment.error,
      };
    }));
  },
    [pages, segmentsByPage],
  );
  const nextQuestionNo = useMemo(
    () => Math.max(0, ...persistedSegments.map((segment) => segment.question_no ?? 0)) + 1,
    [persistedSegments],
  );
  const pendingSegments = useMemo(
    () => allSegments.filter((segment) => (segment.status ?? "pending") === "pending"),
    [allSegments],
  );
  const processingSegments = useMemo(
    () => allSegments.filter((segment) => segment.status === "processing"),
    [allSegments],
  );
  const segmentsWithPages = useMemo(
    () => pages.flatMap((page, pageIndex) => (segmentsByPage[page.id] ?? []).map((segment) => ({ page, pageIndex, segment }))),
    [pages, segmentsByPage],
  );

  useEffect(() => {
    const sessionHash = currentSession?.file_hash;
    if (!sessionHash || pages.length === 0) return;
    const timer = window.setTimeout(() => {
      void updateBatchSession(sessionHash, {
        page_count: pages.length,
        subject,
        notes,
        active_page: activePageIndex,
        segments: persistedSegments,
      }).then((session) => {
        setCurrentSession(session);
        refreshSavedSessions();
      }).catch(() => undefined);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [activePageIndex, currentSession?.file_hash, notes, pages.length, persistedSegments, refreshSavedSessions, subject]);

  useEffect(() => {
    const sessionHash = currentSession?.file_hash;
    if (!sessionHash || processingSegments.length === 0) return;
    let cancelled = false;
    const refreshProcessingStates = () => {
      void getBatchSession(sessionHash).then((session) => {
        if (!session || cancelled) return;
        const states = new Map(session.segments.map((segment) => [segment.id, segment]));
        setCurrentSession(session);
        setSegmentsByPage((current) => Object.fromEntries(
          Object.entries(current).map(([pageId, segments]) => [pageId, segments.map((segment) => {
            const saved = states.get(segment.id);
            return saved ? {
              ...segment,
              questionNo: saved.question_no ?? segment.questionNo,
              status: saved.status,
              taskId: saved.task_id ?? undefined,
              problemIds: saved.problem_ids,
              error: saved.error ?? undefined,
            } : segment;
          })]),
        ));
      }).catch(() => undefined);
    };
    refreshProcessingStates();
    const interval = window.setInterval(refreshProcessingStates, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [currentSession?.file_hash, processingSegments.length]);

  const ensurePdfPageImage = useCallback((scanPage: ScanPage): Promise<File> => {
    if (scanPage.image) return Promise.resolve(scanPage.image);
    const cached = imageCacheRef.current.get(scanPage.id);
    if (cached) {
      imageCacheRef.current.delete(scanPage.id);
      imageCacheRef.current.set(scanPage.id, cached);
      return Promise.resolve(cached);
    }
    if (!scanPage.pdf) return Promise.reject(new Error("扫描页面不可用"));

    const pending = renderPromisesRef.current.get(scanPage.id);
    if (pending) return pending;
    const resource = pdfDocumentsRef.current.get(scanPage.pdf.documentId);
    if (!resource) return Promise.reject(new Error("PDF 已被释放，请重新导入"));

    const promise = renderPdfPage(
      resource.document,
      scanPage.pdf.pageNumber,
      `${scanPage.sourceName}-page-${scanPage.pdf.pageNumber}.png`,
    ).then((image) => {
      imageCacheRef.current.set(scanPage.id, image);
      while (imageCacheRef.current.size > PDF_IMAGE_CACHE_SIZE) {
        const oldestId = imageCacheRef.current.keys().next().value as string | undefined;
        if (!oldestId) break;
        imageCacheRef.current.delete(oldestId);
      }
      setImageCacheVersion((version) => version + 1);
      return image;
    }).finally(() => {
      renderPromisesRef.current.delete(scanPage.id);
    });
    renderPromisesRef.current.set(scanPage.id, promise);
    return promise;
  }, []);

  useEffect(() => {
    const primaryPage = visiblePages[0];
    if (!primaryPage) return;
    let cancelled = false;
    const shouldRenderPrimary = !primaryPage.image && !imageCacheRef.current.has(primaryPage.id);
    setRenderingPageId(shouldRenderPrimary ? primaryPage.id : "");
    let cancelPrefetch: (() => void) | undefined;

    const primaryDelayId = window.setTimeout(() => {
      const renderVisiblePages = async () => {
        await ensurePdfPageImage(primaryPage);
        if (cancelled) return;
        for (const page of visiblePages.slice(1)) {
          await ensurePdfPageImage(page);
          if (cancelled) return;
        }
        const prefetch = async () => {
          const start = activePageIndex + visiblePages.length;
          for (const page of pages.slice(start, start + PREFETCH_PAGE_COUNT)) {
            await ensurePdfPageImage(page);
            if (cancelled) return;
          }
        };
        const startPrefetch = () => {
          void prefetch().catch((reason) => {
            if (!cancelled && !isPdfRenderCancellation(reason)) {
              setError(reason instanceof Error ? reason.message : "预取 PDF 页面失败");
            }
          });
        };
        const idleWindow = window as Window & {
          requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
          cancelIdleCallback?: (id: number) => void;
        };
        const delayId = window.setTimeout(() => {
          if (cancelled) return;
          if (idleWindow.requestIdleCallback) {
            const idleId = idleWindow.requestIdleCallback(startPrefetch, { timeout: 800 });
            cancelPrefetch = () => idleWindow.cancelIdleCallback?.(idleId);
          } else {
            startPrefetch();
          }
        }, PREFETCH_DELAY_MS);
        cancelPrefetch = () => window.clearTimeout(delayId);
      };
      void renderVisiblePages().catch((reason) => {
        if (!cancelled && !isPdfRenderCancellation(reason)) {
          setError(reason instanceof Error ? reason.message : "加载 PDF 页面失败");
        }
      }).finally(() => {
        if (!cancelled) setRenderingPageId((current) => current === primaryPage.id ? "" : current);
      });
    }, PRIMARY_RENDER_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(primaryDelayId);
      cancelPrefetch?.();
    };
  }, [activePageIndex, ensurePdfPageImage, pages, visiblePages]);

  const openWorkspace = useCallback(async (file: File, session: BatchSession | null) => {
    const nextDocuments = new Map<string, PdfDocumentResource>();
    const nextPages: ScanPage[] = [];
    if (isPdf(file)) {
      const documentId = crypto.randomUUID();
      const resource = await openPdf(file);
      nextDocuments.set(documentId, resource);
      const baseName = file.name.replace(/\.pdf$/i, "");
      for (let pageNumber = 1; pageNumber <= resource.document.numPages; pageNumber += 1) {
        nextPages.push({
          id: crypto.randomUUID(),
          label: `${baseName} · 第 ${pageNumber} 页`,
          sourceName: baseName,
          pageNumber,
          pdf: { documentId, pageNumber },
        });
      }
    } else {
      nextPages.push({ id: crypto.randomUUID(), label: file.name, sourceName: file.name, image: file });
    }

    const restoredSegments: Record<string, SegmentedImage[]> = {};
    let restoredQuestionNo = 1;
    for (const segment of session?.segments ?? []) {
      const page = nextPages[segment.page_index];
      if (!page) continue;
      const pageSegments = restoredSegments[page.id] ?? [];
      pageSegments.push({
        id: segment.id,
        filename: `${page.sourceName}-region-${pageSegments.length + 1}.png`,
        mimeType: "image/png",
        rect: { x: segment.x, y: segment.y, width: segment.width, height: segment.height },
        questionNo: segment.question_no ?? restoredQuestionNo,
        status: segment.status ?? "pending",
        taskId: segment.task_id ?? undefined,
        problemIds: segment.problem_ids ?? [],
        error: segment.error ?? undefined,
      });
      restoredQuestionNo = Math.max(restoredQuestionNo, (segment.question_no ?? restoredQuestionNo) + 1);
      restoredSegments[page.id] = pageSegments;
    }

    clearPdfState();
    pdfDocumentsRef.current = nextDocuments;
    setPages(nextPages);
    setSegmentsByPage(restoredSegments);
    setSubject(session?.subject ?? "auto");
    setNotes(session?.notes ?? "");
    setActivePageIndex(Math.min(session?.active_page ?? 0, Math.max(0, nextPages.length - 1)));
    setPageInput(String(Math.min(session?.active_page ?? 0, Math.max(0, nextPages.length - 1)) + 1));
    if (session) setCurrentSession(session);
    notify.success({ title: session ? "已恢复批量扫描进度" : `已载入 ${nextPages.length} 页` });
    return nextPages.length;
  }, [clearPdfState]);

  const importFiles = useCallback(async (picked: File[]) => {
    const file = picked.find((candidate) => candidate.type.startsWith("image/") || isPdf(candidate));
    if (!file) {
      setError("请选择图片或 PDF 文件");
      return;
    }
    setIsImporting(true);
    setError("");
    try {
      const fileHash = await hashFile(file);
      const existing = await getBatchSession(fileHash);
      await openWorkspace(file, existing);
      if (existing) {
        sourceUploadRef.current = null;
        return;
      }

      setIsSavingSource(true);
      const sourceUpload = uploadBatchSource(fileHash, file);
      sourceUploadRef.current = sourceUpload;
      void sourceUpload
        .then((session) => {
          if (sourceUploadRef.current !== sourceUpload) return;
          setCurrentSession(session);
          void refreshSavedSessions();
        })
        .catch((reason) => {
          if (sourceUploadRef.current === sourceUpload) {
            setError(reason instanceof Error ? reason.message : "保存批量扫描文件失败");
          }
        })
        .finally(() => {
          if (sourceUploadRef.current === sourceUpload) setIsSavingSource(false);
        });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导入扫描文件失败");
    } finally {
      setIsImporting(false);
    }
  }, [openWorkspace, refreshSavedSessions]);

  const resumeSession = useCallback(async (session: BatchSession, requestedPage?: number) => {
    setIsImporting(true);
    setError("");
    try {
      const response = await fetch(`/api${session.asset_path}`);
      if (!response.ok) throw new Error("无法读取已保存的原始文件");
      const blob = await response.blob();
      const pageCount = await openWorkspace(new File([blob], session.filename, { type: session.mime_type }), session);
      if (requestedPage && pageCount > 0) {
        const pageIndex = Math.max(0, Math.min(pageCount - 1, requestedPage - 1));
        setActivePageIndex(pageIndex);
        setPageInput(String(pageIndex + 1));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复批量扫描失败");
    } finally {
      setIsImporting(false);
    }
  }, [openWorkspace]);

  useEffect(() => {
    const sessionHash = searchParams.get("session");
    if (!sessionHash || restoredQuerySessionRef.current || pages.length > 0) return;
    const session = savedSessions.find((item) => item.file_hash === sessionHash);
    if (!session) return;
    restoredQuerySessionRef.current = true;
    const requestedPage = Number(searchParams.get("page"));
    void resumeSession(session, Number.isFinite(requestedPage) ? requestedPage : undefined);
  }, [pages.length, resumeSession, savedSessions, searchParams]);

  const submitBatch = useCallback(async () => {
    if (pendingSegments.length === 0 || isSubmitting || isSavingSource) {
      setError("没有待提交的题目区域");
      return;
    }
    setIsSubmitting(true);
    setError("");
    try {
      const savedSession = currentSession ?? await sourceUploadRef.current;
      if (!savedSession) throw new Error("原始扫描文件尚未保存，请稍后重试");
      await updateBatchSession(savedSession.file_hash, {
        page_count: pages.length,
        subject,
        notes,
        active_page: activePageIndex,
        segments: persistedSegments,
      });
      const updates = new Map<string, Partial<SegmentedImage>>();
      const applySegmentUpdate = (segmentId: string, update: Partial<SegmentedImage>) => {
        updates.set(segmentId, update);
        setSegmentsByPage((current) => Object.fromEntries(
          Object.entries(current).map(([pageId, segments]) => [pageId, segments.map((segment) => (
            segment.id === segmentId ? { ...segment, ...update } : segment
          ))]),
        ));
      };
      for (const { page, pageIndex, segment } of segmentsWithPages) {
        if ((segment.status ?? "pending") !== "pending") continue;
        try {
          const blob = await cropSegment(await ensurePdfPageImage(page), segment);
          const created = await createUploadTask({
            subject,
            notes,
            question_no: String(segment.questionNo ?? 0),
            knowledge_tags: [],
            error_tags: [],
            user_tags: [],
            image_base64: await toBase64(blob),
            filename: segment.filename,
            mime_type: segment.mimeType,
            batch_session_hash: savedSession.file_hash,
            batch_segment_id: segment.id,
            batch_page_index: pageIndex,
            batch_question_no: segment.questionNo,
          });
          const taskId = created.task.id;
          applySegmentUpdate(segment.id, { status: "processing", taskId, error: undefined });
          await processTaskInBackground(taskId);
        } catch (reason) {
          applySegmentUpdate(segment.id, {
            status: "failed",
            taskId: updates.get(segment.id)?.taskId,
            error: reason instanceof Error ? reason.message : "提交失败",
          });
        }
      }
      const finalSegments = persistedSegments.map((segment) => {
        const update = updates.get(segment.id);
        return {
          ...segment,
          status: update?.status ?? segment.status,
          task_id: update?.taskId ?? segment.task_id,
          error: update?.error ?? segment.error,
        };
      });
      setSegmentsByPage((current) => Object.fromEntries(
        pages.map((page) => [page.id, (current[page.id] ?? []).map((segment) => ({
          ...segment,
          ...updates.get(segment.id),
        }))]),
      ));
      const updatedSession = await updateBatchSession(savedSession.file_hash, {
        page_count: pages.length,
        subject,
        notes,
        active_page: activePageIndex,
        segments: finalSegments,
      });
      setCurrentSession(updatedSession);
      const failedCount = [...updates.values()].filter((update) => update.status === "failed").length;
      const submittedCount = pendingSegments.length - failedCount;
      notify.success({ title: failedCount ? `已提交 ${submittedCount} 道，${failedCount} 道失败` : `已提交 ${submittedCount} 道题目` });
      await refreshSavedSessions();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量提交失败");
    } finally {
      setIsSubmitting(false);
    }
  }, [activePageIndex, currentSession, ensurePdfPageImage, isSavingSource, isSubmitting, notes, pages, pendingSegments.length, persistedSegments, refreshSavedSessions, segmentsWithPages, subject]);

  const cancelImport = useCallback(() => {
    clearPdfState();
    setPages([]);
    setSegmentsByPage({});
    setActivePageIndex(0);
    setPageInput("1");
    setNotes("");
    setCurrentSession(null);
    sourceUploadRef.current = null;
    setIsSavingSource(false);
    setIsInverted(false);
    setError("");
  }, [clearPdfState]);

  const renderPage = useCallback((page: ScanPage) => {
    const image = page.image ?? imageCacheRef.current.get(page.id);
    if (!image) {
      return (
        <Box key={page.id} className="batch-scan-canvas__empty">
          <Spinner size="large" />
          <Text>{renderingPageId === page.id ? "正在渲染页面…" : "正在准备页面…"}</Text>
        </Box>
      );
    }
    return (
      <BatchSegmenter
        key={page.id}
        file={image}
        initialSegments={segmentsByPage[page.id] ?? []}
        inverted={isInverted}
        nextQuestionNo={nextQuestionNo}
        onOpenTask={(taskId) => window.open(`/tasks/${taskId}`, "_blank", "noopener,noreferrer")}
        onSegmentsChange={(segments) => {
          setSegmentsByPage((current) => ({ ...current, [page.id]: segments }));
        }}
      />
    );
  }, [isInverted, nextQuestionNo, renderingPageId, segmentsByPage]);

  return (
    <Box className={`batch-scan-page${pages.length > 0 ? " is-active" : ""}`}>
      <input
        ref={inputRef}
        className="batch-scan-toolbar__input"
        type="file"
        accept="image/*,application/pdf,.pdf"
        multiple
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) void importFiles(files);
          event.target.value = "";
        }}
      />

      {pages.length === 0 ? (
        <>
          <PageHeader title="批量扫描" description="导入整页图片或 PDF，手动框选每道题后一次提交" />
          <Box className="batch-scan-toolbar">
            <Button variant="primary" onClick={() => inputRef.current?.click()} disabled={isImporting || isSubmitting}>
              <UploadIcon size={16} />
              选择扫描文件
            </Button>
            <Text>支持图片和 PDF，按当前页加载</Text>
            {isImporting && <Text>正在读取 PDF 目录…</Text>}
          </Box>
        </>
      ) : (
        <Box className="batch-scan-workspace-toolbar">
          <IconButton icon={ArrowLeftIcon} size="small" variant="invisible" aria-label="取消本次导入" onClick={cancelImport} />
          <Box className="batch-scan-pager" aria-label="PDF 页码">
            <IconButton
              icon={ChevronLeftIcon}
              size="small"
              variant="invisible"
              aria-label="上一页"
              disabled={activePageIndex === 0}
              onClick={() => goToPage(activePageIndex)}
            />
            <input
              className="batch-scan-pager__input"
              type="text"
              pattern="[0-9]*"
              inputMode="numeric"
              aria-label="跳转到页码"
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
              onBlur={commitPageInput}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") setPageInput(String(activePageIndex + 1));
              }}
            />
            <Text className="batch-scan-pager__total">/ {pages.length}</Text>
            <IconButton
              icon={ChevronRightIcon}
              size="small"
              variant="invisible"
              aria-label="下一页"
              disabled={activePageIndex >= pages.length - 1}
              onClick={() => goToPage(activePageIndex + 2)}
            />
          </Box>
          {isSystemDark && (
            <IconButton
              icon={ContrastIcon}
              size="small"
              variant={isInverted ? "default" : "invisible"}
              aria-label={isInverted ? "恢复原始黑白预览" : "反转黑白预览"}
              title={isInverted ? "恢复原始黑白预览" : "反转黑白预览"}
              onClick={() => setIsInverted((current) => !current)}
            />
          )}
          <Select value={subject} onChange={(event) => setSubject(event.target.value)}>
            <Select.Option value="auto">自动识别学科</Select.Option>
            {SUBJECT_OPTIONS.map((option) => <Select.Option key={option.value} value={option.value}>{option.label}</Select.Option>)}
          </Select>
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="备注（可选）" rows={1} />
          <Text className="batch-scan-workspace-toolbar__count">未提交 {pendingSegments.length} · 处理中 {processingSegments.length}</Text>
          <Button variant="primary" onClick={() => void submitBatch()} disabled={pendingSegments.length === 0 || isSubmitting || isSavingSource}>
            {isSavingSource ? "正在保存原文件…" : isSubmitting ? `正在提交 ${pendingSegments.length} 道…` : `提交 ${pendingSegments.length} 道题目`}
          </Button>
        </Box>
      )}

      {pages.length > 0 && (
        <Box className={`batch-scan-layout${visiblePages.length > 1 ? " is-spread" : ""}`}>
          <Box className="batch-scan-canvas">{visiblePages.map(renderPage)}</Box>
        </Box>
      )}
      {pages.length === 0 && savedSessions.length > 0 && (
        <Box className="batch-scan-history">
          <Box className="batch-scan-history__header">
            <Text className="batch-scan-history__title">最近文件</Text>
            <Text>{savedSessions.length}</Text>
          </Box>
          {savedSessions.slice(0, 5).map((session) => {
            const completed = session.segments.filter((segment) => segment.status === "completed").length;
            const processing = session.segments.filter((segment) => segment.status === "processing").length;
            const pending = session.segments.filter((segment) => segment.status === "pending").length;
            return (
              <Box key={session.file_hash} className="batch-scan-history__item" title={session.file_hash}>
                <Box className="batch-scan-history__mark"><FileTextIcon size={17} /></Box>
                <Box className="batch-scan-history__body">
                  <Text>{session.filename}</Text>
                  <Box className="batch-scan-history__meta">
                    <span>{session.page_count} 页</span>
                    <span>{session.segments.length} 道</span>
                    {completed > 0 && <span>{completed} 已完成</span>}
                    {processing > 0 && <span>{processing} 处理中</span>}
                    {pending > 0 && <span>{pending} 未提交</span>}
                  </Box>
                </Box>
                <Button size="small" variant="default" onClick={() => void resumeSession(session)} disabled={isImporting}>
                  继续框选
                  <ChevronRightIcon size={14} />
                </Button>
              </Box>
            );
          })}
        </Box>
      )}
      {error && <Text className="capture-error" role="alert">{error}</Text>}
    </Box>
  );
}
