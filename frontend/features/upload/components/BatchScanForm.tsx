"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Check,
  Contrast,
  ExternalLink,
  FileText,
  Maximize2,
  Minus,
  PanelLeft,
  PanelRight,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import {
  BatchContinuousSurface,
  BatchCropOverlay,
  buildPageMetrics,
  clamp,
  compareDocumentRects,
  MIN_CROP_SIZE,
  type ContinuousPageSource,
  type DocumentCropRect,
  type SelectionReviewReason,
  type SelectionModel,
  type SelectionStatus,
} from "@/components/batch-continuous";
import { PageHeader } from "@/components/layout/PageHeader";
import { useTheme } from "@/components/providers/ThemeProvider";
import { Box, Button, IconButton, Spinner, Text } from "@/components/ui/primitives";
import { notify } from "@/lib/notify";
import { exportSelectionImage } from "../adapters/batchSelectionExportAdapter";
import { selectionsToSessionSegments, sessionSegmentsToSelections } from "../adapters/batchSessionSelectionAdapter";
import {
  createUploadTask,
  deleteBatchSession,
  getBatchSession,
  listBatchSessions,
  processTaskInBackground,
  type BatchSession,
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

type PdfResource = { document: PdfDocumentHandle; url: string };
type SaveState = "idle" | "saving" | "saved" | "failed";

const FULL_CROP: DocumentCropRect = { x: 0, y: 0, width: 1, height: 1 };
const PAGE_CACHE_LIMIT = 6;
const REVIEW_REASON_LABELS: Record<SelectionReviewReason, string> = {
  unreadable: "扫不到题",
  incomplete: "题目区域不完整",
  multiple_questions: "包含多道完整题目",
  other: "其他异常",
};

function isPdf(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

async function hashFile(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

function selectionAssetFilename(sessionHash: string, segmentId: string, questionNo: number) {
  return `batch-${sessionHash}-${segmentId}-q${questionNo}.png`;
}

async function toBase64(blob: Blob) {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === "string"
      ? resolve(reader.result.split(",").pop() ?? "")
      : reject(new Error("无法读取裁剪图片"));
    reader.onerror = () => reject(reader.error ?? new Error("无法读取裁剪图片"));
    reader.readAsDataURL(blob);
  });
}

async function openPdf(file: File): Promise<PdfResource> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/legacy/build/pdf.worker.min.mjs", import.meta.url).toString();
  const url = URL.createObjectURL(file);
  try {
    const document = await pdfjs.getDocument({ url }).promise;
    return { document: document as unknown as PdfDocumentHandle, url };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

async function renderPdfPage(pdfDocument: PdfDocumentHandle, pageIndex: number, filename: string) {
  const page = await pdfDocument.getPage(pageIndex + 1);
  const viewport = page.getViewport({ scale: 1.5 });
  const output = document.createElement("canvas");
  output.width = Math.ceil(viewport.width);
  output.height = Math.ceil(viewport.height);
  const context = output.getContext("2d");
  if (!context) throw new Error("无法创建 PDF 页面画布");
  await page.render({ canvasContext: context, viewport }).promise;
  const blob = await new Promise<Blob>((resolve, reject) => {
    output.toBlob((value) => value ? resolve(value) : reject(new Error("无法渲染 PDF 页面")), "image/png");
  });
  return new File([blob], `${filename}-page-${pageIndex + 1}.png`, { type: "image/png" });
}

function sortAndNumber(selections: SelectionModel[]) {
  const sorted = [...selections].sort((a, b) => compareDocumentRects(a.rect, b.rect));
  const lockedNumbers = new Set(sorted.filter((selection) => selection.status !== "pending").map((selection) => selection.questionNo));
  let candidate = 1;
  return sorted.map((selection) => {
    if (selection.status !== "pending") return selection;
    while (lockedNumbers.has(candidate)) candidate += 1;
    const questionNo = candidate;
    candidate += 1;
    return { ...selection, questionNo };
  });
}

export function BatchScanForm() {
  const searchParams = useSearchParams();
  const { resolvedTheme } = useTheme();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const zoomRef = useRef(1);
  const sourceFileRef = useRef<File | null>(null);
  const pdfRef = useRef<PdfResource | null>(null);
  const pageFilesRef = useRef(new Map<number, File>());
  const renderPromisesRef = useRef(new Map<number, Promise<File>>());
  const objectUrlsRef = useRef(new Map<number, string>());
  const selectionsRef = useRef<SelectionModel[]>([]);
  const restoredQueryRef = useRef(false);

  const [pages, setPages] = useState<ContinuousPageSource[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [currentSession, setCurrentSession] = useState<BatchSession | null>(null);
  const [savedSessions, setSavedSessions] = useState<BatchSession[]>([]);
  const [crop, setCrop] = useState<DocumentCropRect>(FULL_CROP);
  const [cropConfirmed, setCropConfirmed] = useState(false);
  const [cropView, setCropView] = useState<"edit" | "preview">("edit");
  const [activePageIndex, setActivePageIndex] = useState(0);
  const [visiblePageIndex, setVisiblePageIndex] = useState(0);
  const [pageInput, setPageInput] = useState("1");
  const [selections, setSelections] = useState<SelectionModel[]>([]);
  const [activeSelectionId, setActiveSelectionId] = useState<string>();
  const [zoom, setZoom] = useState(1);
  const [inverted, setInverted] = useState(resolvedTheme === "dark");
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [isImporting, setIsImporting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  selectionsRef.current = selections;
  const metrics = useMemo(() => buildPageMetrics(pages, crop), [crop, pages]);
  const sessionHash = currentSession?.file_hash;
  const activeSelection = selections.find((selection) => selection.id === activeSelectionId);
  const pendingCount = selections.filter((selection) => selection.status === "pending").length;
  const cropTooSmall = crop.width < MIN_CROP_SIZE || crop.height < MIN_CROP_SIZE;

  const refreshSavedSessions = useCallback(async () => {
    try { setSavedSessions(await listBatchSessions()); } catch { /* landing remains usable */ }
  }, []);

  useEffect(() => { void refreshSavedSessions(); }, [refreshSavedSessions]);

  useEffect(() => {
    setInverted(resolvedTheme === "dark");
  }, [resolvedTheme]);

  useEffect(() => {
    if (!pages.length) return;
    const root = document.documentElement;
    root.dataset.oopsnoteBatchScan = "active";
    return () => {
      delete root.dataset.oopsnoteBatchScan;
    };
  }, [pages.length]);

  const clearWorkspace = useCallback(() => {
    if (pdfRef.current) {
      void pdfRef.current.document.destroy?.();
      URL.revokeObjectURL(pdfRef.current.url);
      pdfRef.current = null;
    }
    objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    objectUrlsRef.current.clear();
    pageFilesRef.current.clear();
    renderPromisesRef.current.clear();
    sourceFileRef.current = null;
    setPages([]);
    setImageUrls({});
    setCurrentSession(null);
    setSelections([]);
    setActiveSelectionId(undefined);
    setCrop(FULL_CROP);
    setCropConfirmed(false);
    setCropView("edit");
    setActivePageIndex(0);
    setVisiblePageIndex(0);
    setPageInput("1");
    zoomRef.current = 1;
    setZoom(1);
    setError("");
  }, []);

  useEffect(() => () => clearWorkspace(), [clearWorkspace]);

  const ensurePageFile = useCallback(async (pageIndex: number): Promise<File> => {
    const cached = pageFilesRef.current.get(pageIndex);
    if (cached) {
      pageFilesRef.current.delete(pageIndex);
      pageFilesRef.current.set(pageIndex, cached);
      return cached;
    }
    const pending = renderPromisesRef.current.get(pageIndex);
    if (pending) return pending;
    const source = sourceFileRef.current;
    if (!source) throw new Error("原始文件不可用");
    const promise = pdfRef.current
      ? renderPdfPage(pdfRef.current.document, pageIndex, source.name.replace(/\.pdf$/i, ""))
      : Promise.resolve(source);
    renderPromisesRef.current.set(pageIndex, promise);
    try {
      const file = await promise;
      pageFilesRef.current.set(pageIndex, file);
      while (pageFilesRef.current.size > PAGE_CACHE_LIMIT) {
        const oldest = pageFilesRef.current.keys().next().value as number | undefined;
        if (oldest === undefined) break;
        pageFilesRef.current.delete(oldest);
        const url = objectUrlsRef.current.get(oldest);
        if (url) URL.revokeObjectURL(url);
        objectUrlsRef.current.delete(oldest);
        setImageUrls((current) => {
          const next = { ...current };
          delete next[oldest];
          return next;
        });
      }
      return file;
    } finally {
      renderPromisesRef.current.delete(pageIndex);
    }
  }, []);

  const loadPage = useCallback((pageIndex: number) => {
    if (objectUrlsRef.current.has(pageIndex)) return;
    void ensurePageFile(pageIndex).then((file) => {
      if (objectUrlsRef.current.has(pageIndex)) return;
      const url = URL.createObjectURL(file);
      objectUrlsRef.current.set(pageIndex, url);
      setImageUrls((current) => ({ ...current, [pageIndex]: url }));
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "页面加载失败"));
  }, [ensurePageFile]);

  useEffect(() => { if (pages.length) loadPage(activePageIndex); }, [activePageIndex, loadPage, pages.length]);

  const openWorkspace = useCallback(async (file: File, session: BatchSession | null) => {
    clearWorkspace();
    sourceFileRef.current = file;
    const nextPages: ContinuousPageSource[] = [];
    if (isPdf(file)) {
      const resource = await openPdf(file);
      pdfRef.current = resource;
      const baseName = file.name.replace(/\.pdf$/i, "");
      for (let pageIndex = 0; pageIndex < resource.document.numPages; pageIndex += 1) {
        const page = await resource.document.getPage(pageIndex + 1);
        const viewport = page.getViewport({ scale: 1 });
        nextPages.push({ id: `page-${pageIndex}`, pageIndex, label: `${baseName} · 第 ${pageIndex + 1} 页`, sourceWidth: viewport.width, sourceHeight: viewport.height });
      }
    } else {
      const bitmap = await createImageBitmap(file);
      nextPages.push({ id: "page-0", pageIndex: 0, label: file.name, sourceWidth: bitmap.width, sourceHeight: bitmap.height });
      bitmap.close();
    }
    const nextCrop = session?.crop_rect ?? FULL_CROP;
    const nextMetrics = buildPageMetrics(nextPages, nextCrop);
    const nextSelections = sortAndNumber(sessionSegmentsToSelections(session?.segments ?? [], nextMetrics));
    setPages(nextPages);
    setCrop(nextCrop);
    setCropConfirmed(session?.crop_confirmed ?? false);
    setCropView(session?.crop_confirmed ? "preview" : "edit");
    setSelections(nextSelections);
    setCurrentSession(session);
    const pageIndex = Math.min(session?.active_page ?? 0, Math.max(0, nextPages.length - 1));
    setActivePageIndex(pageIndex);
    setVisiblePageIndex(pageIndex);
    setPageInput(String(pageIndex + 1));
    notify.success({ title: session ? "已恢复批量扫描" : `已载入 ${nextPages.length} 页` });
  }, [clearWorkspace]);

  const importFile = useCallback(async (file: File) => {
    setIsImporting(true);
    setError("");
    try {
      const fileHash = await hashFile(file);
      const existing = await getBatchSession(fileHash);
      await openWorkspace(file, existing);
      if (!existing) {
        const session = await uploadBatchSource(fileHash, file);
        setCurrentSession(session);
        await refreshSavedSessions();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导入失败");
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
      const file = new File([await response.blob()], session.filename, { type: session.mime_type });
      await openWorkspace(file, session);
      if (requestedPage) {
        const pageIndex = clamp(requestedPage - 1, 0, Math.max(0, session.page_count - 1));
        setActivePageIndex(pageIndex);
        setVisiblePageIndex(pageIndex);
        setPageInput(String(pageIndex + 1));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复批量扫描失败");
    } finally {
      setIsImporting(false);
    }
  }, [openWorkspace]);

  useEffect(() => {
    const fileHash = searchParams.get("session");
    if (!fileHash || restoredQueryRef.current || pages.length || !savedSessions.length) return;
    const session = savedSessions.find((item) => item.file_hash === fileHash);
    if (!session) return;
    restoredQueryRef.current = true;
    const requestedPage = Number(searchParams.get("page"));
    void resumeSession(session, Number.isFinite(requestedPage) ? requestedPage : undefined);
  }, [pages.length, resumeSession, savedSessions, searchParams]);

  const persistSession = useCallback(async (
    nextSelections = selectionsRef.current,
    overrides: Partial<Pick<BatchSession, "crop_rect" | "crop_confirmed" | "active_page">> = {},
  ) => {
    if (!sessionHash || !pages.length) return null;
    setSaveState("saving");
    try {
      const session = await updateBatchSession(sessionHash, {
        page_count: pages.length,
        active_page: overrides.active_page ?? visiblePageIndex,
        crop_rect: overrides.crop_rect ?? crop,
        crop_confirmed: overrides.crop_confirmed ?? cropConfirmed,
        segments: selectionsToSessionSegments(nextSelections),
      });
      setCurrentSession(session);
      setSaveState("saved");
      return session;
    } catch (reason) {
      setSaveState("failed");
      throw reason;
    }
  }, [crop, cropConfirmed, pages.length, sessionHash, visiblePageIndex]);

  useEffect(() => {
    if (!sessionHash || !pages.length) return;
    const timer = window.setTimeout(() => {
      void persistSession().catch(() => undefined);
    }, 650);
    return () => window.clearTimeout(timer);
  }, [crop, cropConfirmed, pages.length, persistSession, selections, sessionHash]);

  useEffect(() => {
    if (saveState !== "failed" || !sessionHash) return;
    const timer = window.setTimeout(() => {
      void persistSession().catch(() => undefined);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [persistSession, saveState, sessionHash]);

  useEffect(() => {
    if (!selections.some((selection) => selection.status === "processing") || !currentSession) return;
    const timer = window.setInterval(() => {
      void getBatchSession(currentSession.file_hash).then((session) => {
        if (!session) return;
        const restored = sortAndNumber(sessionSegmentsToSelections(session.segments, buildPageMetrics(pages, session.crop_rect)));
        setSelections(restored);
        setCurrentSession(session);
      }).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [currentSession, pages, selections]);

  const goToPage = useCallback((pageIndex: number) => {
    const target = clamp(pageIndex, 0, Math.max(0, pages.length - 1));
    setActivePageIndex(target);
    setVisiblePageIndex(target);
    setPageInput(String(target + 1));
    loadPage(target);
    if (cropConfirmed || cropView === "preview") {
      const page = viewportRef.current?.querySelector<HTMLElement>(`[data-page-index="${target}"]`);
      page?.scrollIntoView({ block: "start" });
    }
  }, [cropConfirmed, cropView, loadPage, pages.length]);

  const updateSelections = useCallback((next: SelectionModel[]) => {
    setSelections(sortAndNumber(next));
  }, []);

  const deleteActiveSelection = useCallback(() => {
    if (!activeSelection || activeSelection.status !== "pending") return;
    updateSelections(selectionsRef.current.filter((selection) => selection.id !== activeSelection.id));
    setActiveSelectionId(undefined);
  }, [activeSelection, updateSelections]);

  const submitPending = useCallback(async () => {
    if (!currentSession || isSubmitting) return;
    const pending = selectionsRef.current.filter((selection) => selection.status === "pending");
    if (!pending.length) return;
    setIsSubmitting(true);
    setError("");
    for (const original of pending) {
      let working = selectionsRef.current;
      try {
        await persistSession(working);
        const blob = await exportSelectionImage(original, crop, ensurePageFile);
        const created = await createUploadTask({
          subject: "auto",
          notes: "",
          question_no: String(original.questionNo),
          knowledge_tags: [],
          error_tags: [],
          user_tags: [],
          image_base64: await toBase64(blob),
          filename: selectionAssetFilename(currentSession.file_hash, original.id, original.questionNo),
          mime_type: "image/png",
          batch_session_hash: currentSession.file_hash,
          batch_segment_id: original.id,
          batch_page_index: original.slices[0]?.pageIndex ?? 0,
          batch_question_no: original.questionNo,
        });
        working = selectionsRef.current.map((selection) => selection.id === original.id
          ? { ...selection, status: "processing" as const, taskId: created.task.id, error: undefined }
          : selection);
        setSelections(working);
        selectionsRef.current = working;
        await persistSession(working);
        await processTaskInBackground(created.task.id);
      } catch (reason) {
        working = selectionsRef.current.map((selection) => selection.id === original.id
          ? { ...selection, status: "failed" as const, error: reason instanceof Error ? reason.message : "提交失败" }
          : selection);
        setSelections(working);
        selectionsRef.current = working;
        void persistSession(working).catch(() => undefined);
      }
    }
    setIsSubmitting(false);
  }, [crop, currentSession, ensurePageFile, isSubmitting, persistSession]);

  const retrySelection = useCallback(async (selection: SelectionModel) => {
    if (!selection.taskId) return;
    const next = selectionsRef.current.map((item) => item.id === selection.id ? {
      ...item,
      status: "processing" as const,
      error: undefined,
      reviewReason: undefined,
      reviewPreviousStatus: undefined,
      reviewResolved: false,
    } : item);
    setSelections(next);
    try {
      await persistSession(next);
      await processTaskInBackground(selection.taskId);
    } catch (reason) {
      setSelections((current) => current.map((item) => item.id === selection.id
        ? { ...item, status: "failed", error: reason instanceof Error ? reason.message : "重试失败" }
        : item));
    }
  }, [persistSession]);

  const markSelectionReview = useCallback(async (selection: SelectionModel, reason: SelectionReviewReason | "") => {
    const nextStatus: SelectionStatus = reason
      ? "needs_review"
      : (selection.reviewPreviousStatus ?? (selection.taskId ? "completed" : "pending"));
    const next = selectionsRef.current.map((item) => item.id === selection.id
      ? {
          ...item,
          status: nextStatus,
          reviewReason: reason || undefined,
          reviewPreviousStatus: reason ? (item.status === "needs_review" ? item.reviewPreviousStatus : item.status) : undefined,
          reviewResolved: !reason,
        }
      : item);
    setSelections(next);
    selectionsRef.current = next;
    try {
      await persistSession(next);
    } catch {
      // Keep the local marker visible; autosave retry will persist it later.
    }
  }, [persistSession]);

  const fitWidth = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    setZoom(clamp((viewport.clientWidth - 40) / 820, 0.25, 3));
  }, []);

  const setZoomAroundPointer = useCallback((nextZoom: number, clientX?: number, clientY?: number) => {
    const viewport = viewportRef.current;
    const bounded = clamp(nextZoom, 0.25, 3);
    const previousZoom = zoomRef.current;
    zoomRef.current = bounded;
    if (!viewport || clientX === undefined || clientY === undefined) {
      setZoom(bounded);
      return;
    }
    const bounds = viewport.getBoundingClientRect();
    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const ratio = bounded / previousZoom;
    viewport.scrollLeft = (viewport.scrollLeft + x) * ratio - x;
    viewport.scrollTop = (viewport.scrollTop + y) * ratio - y;
    setZoom(bounded);
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      setZoomAroundPointer(
        zoomRef.current * (event.deltaY > 0 ? 0.9 : 1.1),
        event.clientX,
        event.clientY,
      );
    };
    viewport.addEventListener("wheel", handleWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleWheel);
  }, [pages.length, setZoomAroundPointer]);

  const renderDocument = cropConfirmed || cropView === "preview";
  const cropOverlayScaleStyle = {
    "--batch-crop-stroke": `${3 * zoom}px`,
    "--batch-crop-offset": `${1.5 * zoom}px`,
    "--batch-selection-radius": `${5 * zoom}px`,
    "--batch-handle-stroke": `${3 * zoom}px`,
    "--batch-handle-offset": `${1.5 * zoom}px`,
    "--batch-handle-negative-offset": `${-1.5 * zoom}px`,
    "--batch-handle-hit": `${16 * zoom}px`,
    "--batch-handle-side-hit": `${44 * zoom}px`,
    "--batch-handle-length": `${36 * zoom}px`,
    "--batch-corner-hit": `${32 * zoom}px`,
    "--batch-corner-length": `${22 * zoom}px`,
    "--batch-corner-radius": `${5 * zoom}px`,
  } as React.CSSProperties;

  return (
    <Box className={`batch-scan-page${pages.length ? " is-active" : ""}`}>
      <input
        ref={inputRef}
        className="batch-scan-toolbar__input"
        type="file"
        accept="image/*,application/pdf,.pdf"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void importFile(file);
          event.target.value = "";
        }}
      />

      {!pages.length ? (
        <>
          <PageHeader title="批量扫描" description="先统一裁剪页面，再在连续文档上框选题目" />
          <Box className="batch-scan-toolbar">
            <Button variant="primary" onClick={() => inputRef.current?.click()} disabled={isImporting}>
              <Upload size={16} />{isImporting ? "正在载入" : "选择 PDF 或图片"}
            </Button>
            {isImporting && <Spinner size="small" />}
          </Box>
          {savedSessions.length > 0 && (
            <Box className="batch-scan-history">
              <Box className="batch-scan-history__header"><Text className="batch-scan-history__title">最近文件</Text><Text>{savedSessions.length}</Text></Box>
              {savedSessions.slice(0, 8).map((session) => (
                <Box key={session.file_hash} className="batch-scan-history__item">
                  <Box className="batch-scan-history__mark"><FileText size={17} /></Box>
                  <Box className="batch-scan-history__body">
                    <Text>{session.filename}</Text>
                    <Box className="batch-scan-history__meta"><span>{session.page_count} 页</span><span>{session.segments.length} 道</span></Box>
                  </Box>
                  <Button size="small" variant="default" onClick={() => void resumeSession(session)} disabled={isImporting}>继续</Button>
                  <IconButton icon={Trash2} size="small" variant="invisible" aria-label="删除最近文件" title="删除最近文件" onClick={() => {
                      if (!window.confirm("删除整次批量扫描记录？已生成的任务和题目会保留。")) return;
                      void deleteBatchSession(session.file_hash).then(refreshSavedSessions);
                    }} />
                </Box>
              ))}
            </Box>
          )}
        </>
      ) : (
        <>
          <Box className="batch-workflow-toolbar">
            <IconButton icon={ArrowLeft} variant="invisible" aria-label="返回最近文件" title="返回最近文件" onClick={clearWorkspace} />
            <IconButton icon={PanelLeft} variant={leftOpen ? "default" : "invisible"} aria-label="切换页面栏" title="切换页面栏" onClick={() => setLeftOpen((value) => !value)} />
            <IconButton icon={PanelRight} variant={rightOpen ? "default" : "invisible"} aria-label="切换选框栏" title="切换选框栏" onClick={() => setRightOpen((value) => !value)} />
            <span className={`batch-save-state is-${saveState}`}>
              {saveState === "saving" ? "正在保存" : saveState === "failed" ? "保存失败，正在重试" : saveState === "saved" ? "已保存" : "尚未修改"}
            </span>
            <span className="batch-workflow-toolbar__spacer" />
            {cropConfirmed && (
              <>
                <IconButton icon={Trash2} variant="invisible" aria-label="删除当前选框" title="删除当前选框" disabled={!activeSelection || activeSelection.status !== "pending"} onClick={deleteActiveSelection} />
                <IconButton icon={Contrast} variant={inverted ? "default" : "invisible"} aria-label="反色预览" title="反色预览" onClick={() => setInverted((value) => !value)} />
                <Button variant="primary" disabled={!pendingCount || isSubmitting} onClick={() => void submitPending()}>
                  {isSubmitting ? "正在提交" : `提交 ${pendingCount} 道题目`}
                </Button>
              </>
            )}
            {!cropConfirmed && cropView === "edit" && <Button variant="default" disabled={cropTooSmall} onClick={() => setCropView("preview")}>检查裁剪</Button>}
            {!cropConfirmed && cropView === "preview" && <Button variant="default" onClick={() => setCropView("edit")}>调整裁剪框</Button>}
            {!cropConfirmed && cropView === "preview" && (
              <Button variant="primary" disabled={cropTooSmall} onClick={() => {
                setCropConfirmed(true);
                void persistSession([], { crop_rect: crop, crop_confirmed: true }).catch(() => undefined);
              }}><Check size={16} />确认裁剪并开始框题</Button>
            )}
          </Box>

          <Box className={`batch-continuous-workspace${leftOpen ? " has-left" : ""}${rightOpen && cropConfirmed ? " has-right" : ""}`}>
            {leftOpen && (
              <aside className="batch-page-rail" aria-label="页面导航">
                <Text className="batch-rail-title">页面</Text>
                <nav>{pages.map((page) => (
                  <button type="button" key={page.id} aria-label={`第 ${page.pageIndex + 1} 页`} className={(renderDocument ? visiblePageIndex : activePageIndex) === page.pageIndex ? "is-active" : ""} onClick={() => goToPage(page.pageIndex)}>
                    <span>{page.pageIndex + 1}</span>
                  </button>
                ))}</nav>
              </aside>
            )}

            <main className="batch-document-column">
              <Box className="batch-pdf-controls">
                <IconButton icon={Minus} size="small" variant="invisible" aria-label="缩小" title="缩小" onClick={() => setZoomAroundPointer(zoom - 0.1)} />
                <span>{Math.round(zoom * 100)}%</span>
                <IconButton icon={Plus} size="small" variant="invisible" aria-label="放大" title="放大" onClick={() => setZoomAroundPointer(zoom + 0.1)} />
                <IconButton icon={Maximize2} size="small" variant="invisible" aria-label="适合宽度" title="适合宽度" onClick={fitWidth} />
                <label className="batch-page-input"><input value={pageInput} inputMode="numeric" onChange={(event) => setPageInput(event.target.value)} onBlur={() => goToPage(Number(pageInput) - 1)} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} /><span>/ {pages.length}</span></label>
              </Box>
              <div
                ref={viewportRef}
                className="batch-document-viewport"
              >
                {renderDocument ? (
                  <BatchContinuousSurface
                    pages={pages}
                    crop={crop}
                    imageUrls={imageUrls}
                    loadPage={loadPage}
                    selections={cropConfirmed ? selections : []}
                    activeSelectionId={activeSelectionId}
                    inverted={inverted}
                    zoom={zoom}
                    viewportRef={viewportRef}
                    onVisiblePageChange={(pageIndex) => { setVisiblePageIndex(pageIndex); setPageInput(String(pageIndex + 1)); }}
                    onActiveSelectionChange={setActiveSelectionId}
                    onSelectionCreate={(selection) => updateSelections([...selectionsRef.current, selection])}
                    onSelectionChange={(selection) => updateSelections(selectionsRef.current.map((item) => item.id === selection.id ? selection : item))}
                    onTooSmall={() => notify.error({ title: "选区过小" })}
                    selectionEnabled={cropConfirmed}
                  />
                ) : (
                  <div className={`batch-crop-editor${inverted ? " is-inverted" : ""}`} style={{ ...cropOverlayScaleStyle, width: `${Math.round(820 * zoom)}px`, aspectRatio: `${pages[activePageIndex].sourceWidth} / ${pages[activePageIndex].sourceHeight}` }}>
                    {imageUrls[activePageIndex] ? <img src={imageUrls[activePageIndex]} alt={pages[activePageIndex].label} draggable={false} /> : <Spinner />}
                    <BatchCropOverlay
                      value={crop}
                      onChange={setCrop}
                      onTooSmall={() => notify.error({ title: `裁剪区域过小，宽高至少为页面的 ${Math.round(MIN_CROP_SIZE * 100)}%` })}
                    />
                  </div>
                )}
              </div>
            </main>

            {rightOpen && cropConfirmed && (
              <aside className="batch-selection-rail" aria-label="选框列表">
                <Box className="batch-selection-rail__header"><Text className="batch-rail-title">题目选框</Text><Text>{selections.length}</Text></Box>
                <div className="batch-selection-list">
                  {selections.map((selection) => (
                    <div
                      key={selection.id}
                      className={`batch-selection-list__item${selection.id === activeSelectionId ? " is-active" : ""}`}
                    >
                      <button
                        type="button"
                        className="batch-selection-list__primary"
                        onClick={() => {
                          setActiveSelectionId(selection.id);
                          const y = selection.rect.top / Math.max(1, metrics.at(-1)?.documentBottom ?? 1);
                          if (viewportRef.current) viewportRef.current.scrollTop = y * viewportRef.current.scrollHeight - 80;
                        }}
                      >
                        <span className={`batch-selection-list__number is-${selection.status}`}>{selection.questionNo}</span>
                        <span><strong>第 {selection.slices[0]?.pageIndex + 1}{selection.slices.length > 1 ? `–${selection.slices.at(-1)!.pageIndex + 1}` : ""} 页</strong><small>{selection.status === "pending" ? "待提交" : selection.status === "processing" ? "处理中" : selection.status === "completed" ? "已完成" : selection.status === "needs_review" ? `需人工复核：${selection.reviewReason ? REVIEW_REASON_LABELS[selection.reviewReason] : "异常"}` : selection.error || "失败"}</small></span>
                      </button>
                      <label className="batch-selection-list__review" title="标记或取消人工复核">
                        <AlertTriangle size={14} aria-hidden="true" />
                        <select
                          aria-label={`第 ${selection.questionNo} 题异常状态`}
                          value={selection.reviewReason ?? ""}
                          onChange={(event) => void markSelectionReview(selection, event.target.value as SelectionReviewReason | "")}
                        >
                          <option value="">无异常</option>
                          {(Object.keys(REVIEW_REASON_LABELS) as SelectionReviewReason[]).map((reason) => (
                            <option key={reason} value={reason}>{REVIEW_REASON_LABELS[reason]}</option>
                          ))}
                        </select>
                      </label>
                      {(selection.status === "failed" || (selection.status === "needs_review" && selection.reviewPreviousStatus === "failed")) && selection.taskId && <IconButton icon={RefreshCw} size="small" variant="invisible" aria-label="重试" title="使用同一截图重试" onClick={() => void retrySelection(selection)} />}
                      {(selection.status === "completed" || selection.status === "needs_review") && selection.taskId && <IconButton icon={ExternalLink} size="small" variant="invisible" aria-label="打开任务" title="打开任务" onClick={() => window.open(`/tasks/${selection.taskId}`, "_blank", "noopener,noreferrer")} />}
                    </div>
                  ))}
                  {!selections.length && <Text className="batch-selection-list__empty">在页面上拖动以创建题目选框</Text>}
                </div>
              </aside>
            )}
          </Box>
        </>
      )}

      {error && <Box className="batch-scan-error" role="alert"><AlertCircle size={16} /><span>{error}</span></Box>}
    </Box>
  );
}
