"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Check,
  Contrast,
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
  buildPageMetrics,
  clamp,
  DEFAULT_COLUMN_LAYOUT,
  documentRectFromSlices,
  MIN_CROP_SIZE,
  type ColumnLayout,
  type ContinuousPageSource,
  type DocumentCropRect,
  type SelectionReviewReason,
  type SelectionModel,
  type SelectionStatus,
} from "@/components/batch-continuous";
import { ImageSelectionStage, NormalizedRectEditor } from "@/components/image-selection";
import { PageHeader } from "@/components/layout/PageHeader";
import { useTheme } from "@/components/providers/ThemeProvider";
import { Box, Button, IconButton, Spinner, Text } from "@/components/ui/primitives";
import { RenameDialog } from "@/components/ui/RenameDialog";
import { notify } from "@/lib/notify";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiErrorFromResponse, fetchApi } from "@/lib/api";
import { selectionsToSessionSegments, sessionSegmentsToSelections } from "../adapters/batchSessionSelectionAdapter";
import {
  deleteBatchSession,
  getBatchUploadLimits,
  getBatchSession,
  listBatchSessions,
  processBatchSession,
  processTaskInBackground,
  type BatchSession,
  updateBatchSession,
  uploadBatchSource,
} from "../api";
import {
  FULL_CROP,
  PAGE_CACHE_LIMIT,
  buildSessionContentSnapshot,
  hashFile,
  isPdf,
  nearestAvailablePageIndex,
  openPdf,
  projectBatchSession,
  renderPdfPage,
  sortAndNumber,
  upsertBatchSession,
  type PdfResource,
  type SaveState,
} from "./batchScanSupport";
import { BatchSessionHistory } from "./BatchSessionHistory";
import { BatchSelectionRail } from "./BatchSelectionRail";

class StaleWorkspaceError extends Error {
  constructor() {
    super("批量扫描工作区已切换");
    this.name = "StaleWorkspaceError";
  }
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
  const workspaceGenerationRef = useRef(0);
  const selectionsRef = useRef<SelectionModel[]>([]);
  const visiblePageIndexRef = useRef(0);
  const currentContentSnapshotRef = useRef("");
  const persistedContentSnapshotRef = useRef("");
  const sessionRevisionRef = useRef(0);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const submissionRef = useRef(false);
  const restoredQueryRef = useRef(false);

  const [pages, setPages] = useState<ContinuousPageSource[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [currentSession, setCurrentSession] = useState<BatchSession | null>(null);
  const [savedSessions, setSavedSessions] = useState<BatchSession[]>([]);
  const [crop, setCrop] = useState<DocumentCropRect>(FULL_CROP);
  const [columnLayout, setColumnLayout] = useState<ColumnLayout>({ ...DEFAULT_COLUMN_LAYOUT });
  const [excludedPageIndices, setExcludedPageIndices] = useState<number[]>([]);
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
  const [renameTarget, setRenameTarget] = useState<BatchSession | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [isRenaming, setIsRenaming] = useState(false);

  selectionsRef.current = selections;
  const excludedPageSet = useMemo(() => new Set(excludedPageIndices), [excludedPageIndices]);
  const activePages = useMemo(() => pages.filter((page) => !excludedPageSet.has(page.pageIndex)), [excludedPageSet, pages]);
  const metrics = useMemo(() => buildPageMetrics(activePages, crop, columnLayout), [activePages, columnLayout, crop]);
  const sessionHash = currentSession?.file_hash;
  const activeSelection = selections.find((selection) => selection.id === activeSelectionId);
  const pendingCount = selections.filter((selection) => selection.status === "pending").length;
  const cropTooSmall = crop.width < MIN_CROP_SIZE || crop.height < MIN_CROP_SIZE;
  const contentSnapshot = useMemo(() => buildSessionContentSnapshot(
    pages.length,
    crop,
    cropConfirmed,
    columnLayout,
    excludedPageIndices,
    selections,
  ), [columnLayout, crop, cropConfirmed, excludedPageIndices, pages.length, selections]);
  visiblePageIndexRef.current = visiblePageIndex;
  currentContentSnapshotRef.current = contentSnapshot;

  const refreshSavedSessions = useCallback(async () => {
    try { setSavedSessions(await listBatchSessions()); } catch { /* landing remains usable */ }
  }, []);

  const openRenameSession = useCallback((session: BatchSession) => {
    setRenameTarget(session);
    setRenameValue(session.filename);
  }, []);

  const renameSession = useCallback(async () => {
    if (!renameTarget) return;
    const session = renameTarget;
    const filename = renameValue.trim();
    if (!filename || filename === session.filename) return;
    setIsRenaming(true);
    try {
      await updateBatchSession(session.file_hash, session.revision, {
        filename,
        page_count: session.page_count,
        active_page: session.active_page,
        crop_rect: session.crop_rect,
        crop_confirmed: session.crop_confirmed,
        column_layout: session.column_layout ?? { column_count: 1, overlap_ratio: 0.5 },
        excluded_page_indices: session.excluded_page_indices ?? [],
        segments: session.segments,
      });
      await refreshSavedSessions();
      setRenameTarget(null);
      notify.success({ title: "文件已重命名" });
    } catch (reason) {
      await refreshSavedSessions();
      notify.error({ title: reason instanceof Error ? reason.message : "重命名文件失败" });
    } finally {
      setIsRenaming(false);
    }
  }, [refreshSavedSessions, renameTarget, renameValue]);

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
    workspaceGenerationRef.current += 1;
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
    setColumnLayout({ ...DEFAULT_COLUMN_LAYOUT });
    setExcludedPageIndices([]);
    setCropConfirmed(false);
    setCropView("edit");
    setActivePageIndex(0);
    setVisiblePageIndex(0);
    setPageInput("1");
    zoomRef.current = 1;
    setZoom(1);
    setSaveState("idle");
    currentContentSnapshotRef.current = "";
    persistedContentSnapshotRef.current = "";
    sessionRevisionRef.current = 0;
    saveQueueRef.current = Promise.resolve();
    submissionRef.current = false;
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
    const generation = workspaceGenerationRef.current;
    const pdfDocument = pdfRef.current?.document;
    const promise = pdfDocument
      ? renderPdfPage(pdfDocument, pageIndex, source.name.replace(/\.pdf$/i, ""))
      : Promise.resolve(source);
    renderPromisesRef.current.set(pageIndex, promise);
    try {
      const file = await promise;
      if (workspaceGenerationRef.current !== generation) throw new StaleWorkspaceError();
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
      if (renderPromisesRef.current.get(pageIndex) === promise) {
        renderPromisesRef.current.delete(pageIndex);
      }
    }
  }, []);

  const loadPage = useCallback((pageIndex: number) => {
    if (objectUrlsRef.current.has(pageIndex)) return;
    const generation = workspaceGenerationRef.current;
    void ensurePageFile(pageIndex).then((file) => {
      if (workspaceGenerationRef.current !== generation) return;
      if (objectUrlsRef.current.has(pageIndex)) return;
      const url = URL.createObjectURL(file);
      objectUrlsRef.current.set(pageIndex, url);
      setImageUrls((current) => ({ ...current, [pageIndex]: url }));
    }).catch((reason) => {
      if (!(reason instanceof StaleWorkspaceError)) {
        notify.error({ id: "batch-operation-error", title: reason instanceof Error ? reason.message : "页面加载失败" });
      }
    });
  }, [ensurePageFile]);

  useEffect(() => { if (pages.length) loadPage(activePageIndex); }, [activePageIndex, loadPage, pages.length]);

  const openWorkspace = useCallback(async (file: File, session: BatchSession | null) => {
    clearWorkspace();
    const generation = workspaceGenerationRef.current;
    sourceFileRef.current = file;
    const nextPages: ContinuousPageSource[] = [];
    if (isPdf(file)) {
      const resource = await openPdf(file);
      if (workspaceGenerationRef.current !== generation) {
        await resource.document.destroy?.();
        URL.revokeObjectURL(resource.url);
        throw new StaleWorkspaceError();
      }
      pdfRef.current = resource;
      const baseName = file.name.replace(/\.pdf$/i, "");
      for (let pageIndex = 0; pageIndex < resource.document.numPages; pageIndex += 1) {
        const page = await resource.document.getPage(pageIndex + 1);
        if (workspaceGenerationRef.current !== generation) throw new StaleWorkspaceError();
        const viewport = page.getViewport({ scale: 1 });
        nextPages.push({ id: `page-${pageIndex}`, pageIndex, label: `${baseName} · 第 ${pageIndex + 1} 页`, sourceWidth: viewport.width, sourceHeight: viewport.height });
      }
    } else {
      const bitmap = await createImageBitmap(file);
      if (workspaceGenerationRef.current !== generation) {
        bitmap.close();
        throw new StaleWorkspaceError();
      }
      nextPages.push({ id: "page-0", pageIndex: 0, label: file.name, sourceWidth: bitmap.width, sourceHeight: bitmap.height });
      bitmap.close();
    }
    if (workspaceGenerationRef.current !== generation) throw new StaleWorkspaceError();
    const nextCrop = session?.crop_rect ?? FULL_CROP;
    const nextColumnLayout: ColumnLayout = {
      columnCount: session?.column_layout?.column_count ?? 1,
      overlapRatio: session?.column_layout?.overlap_ratio ?? 0.5,
    };
    const nextExcludedPageIndices = session?.excluded_page_indices ?? [];
    const nextActivePages = nextPages.filter((page) => !nextExcludedPageIndices.includes(page.pageIndex));
    const nextMetrics = buildPageMetrics(nextActivePages, nextCrop, nextColumnLayout);
    const nextSelections = sortAndNumber(sessionSegmentsToSelections(session?.segments ?? [], nextMetrics));
    const restoredSnapshot = buildSessionContentSnapshot(
      nextPages.length,
      nextCrop,
      session?.crop_confirmed ?? false,
      nextColumnLayout,
      nextExcludedPageIndices,
      nextSelections,
    );
    currentContentSnapshotRef.current = restoredSnapshot;
    persistedContentSnapshotRef.current = restoredSnapshot;
    sessionRevisionRef.current = session?.revision ?? 0;
    setPages(nextPages);
    setCrop(nextCrop);
    setColumnLayout(nextColumnLayout);
    setExcludedPageIndices(nextExcludedPageIndices);
    setCropConfirmed(session?.crop_confirmed ?? false);
    setCropView(session?.crop_confirmed ? "preview" : "edit");
    setSelections(nextSelections);
    setCurrentSession(session);
    setSaveState(session ? "saved" : "idle");
    const pageIndex = nearestAvailablePageIndex(nextPages, nextExcludedPageIndices, session?.active_page ?? 0);
    setActivePageIndex(pageIndex);
    setVisiblePageIndex(pageIndex);
    setPageInput(String(pageIndex + 1));
    notify.success({ title: session ? "已恢复批量扫描" : `已载入 ${nextPages.length} 页` });
  }, [clearWorkspace]);

  const importFile = useCallback(async (file: File) => {
    setIsImporting(true);
    try {
      const { source_max_bytes: sourceMaxBytes } = await getBatchUploadLimits();
      if (file.size > sourceMaxBytes) {
        const maxMiB = Math.floor(sourceMaxBytes / (1024 * 1024));
        throw new Error(`文件超过批量导入上限（${maxMiB} MiB），请压缩或拆分后重试`);
      }
      const fileHash = await hashFile(file);
      const existing = await getBatchSession(fileHash);
      await openWorkspace(file, existing);
      if (!existing) {
        const pageCount = pdfRef.current?.document.numPages ?? 1;
        const session = await uploadBatchSource(fileHash, file, pageCount);
        sessionRevisionRef.current = session.revision;
        setCurrentSession(session);
        setSaveState("saved");
        await refreshSavedSessions();
      }
    } catch (reason) {
      if (!(reason instanceof StaleWorkspaceError)) {
        notify.error({ id: "batch-operation-error", title: reason instanceof Error ? reason.message : "导入失败" });
      }
    } finally {
      setIsImporting(false);
    }
  }, [openWorkspace, refreshSavedSessions]);

  const resumeSession = useCallback(async (session: BatchSession, requestedPage?: number) => {
    setIsImporting(true);
    try {
      const response = await fetchApi(session.asset_path);
      if (!response.ok) throw await apiErrorFromResponse(response);
      const file = new File([await response.blob()], session.filename, { type: session.mime_type });
      await openWorkspace(file, session);
      if (requestedPage) {
        const sourcePages = Array.from({ length: session.page_count }, (_, pageIndex) => ({ pageIndex }));
        const pageIndex = nearestAvailablePageIndex(
          sourcePages,
          session.excluded_page_indices ?? [],
          clamp(requestedPage - 1, 0, Math.max(0, session.page_count - 1)),
        );
        setActivePageIndex(pageIndex);
        setVisiblePageIndex(pageIndex);
        setPageInput(String(pageIndex + 1));
      }
    } catch (reason) {
      if (!(reason instanceof StaleWorkspaceError)) {
        notify.error({ id: "batch-operation-error", title: reason instanceof Error ? reason.message : "恢复批量扫描失败" });
      }
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

  const applyServerSession = useCallback((session: BatchSession, replaceLocal: boolean) => {
    const projected = projectBatchSession(session, pages);
    persistedContentSnapshotRef.current = projected.snapshot;
    sessionRevisionRef.current = session.revision;
    setCurrentSession(session);
    setSavedSessions((current) => upsertBatchSession(current, session));
    if (replaceLocal) {
      currentContentSnapshotRef.current = projected.snapshot;
      selectionsRef.current = projected.selections;
      setSelections(projected.selections);
      setCrop(session.crop_rect);
      setCropConfirmed(session.crop_confirmed);
      setColumnLayout(projected.columnLayout);
      setExcludedPageIndices(session.excluded_page_indices ?? []);
    }
    return projected;
  }, [pages]);

  const persistSession = useCallback((
    nextSelections = selectionsRef.current,
    overrides: Partial<Pick<BatchSession, "crop_rect" | "crop_confirmed" | "active_page" | "excluded_page_indices">> & { columnLayout?: ColumnLayout } = {},
  ) => {
    if (!sessionHash || !pages.length) return Promise.resolve(null);
    const nextCrop = overrides.crop_rect ?? crop;
    const nextCropConfirmed = overrides.crop_confirmed ?? cropConfirmed;
    const nextColumnLayout = overrides.columnLayout ?? columnLayout;
    const nextExcludedPageIndices = overrides.excluded_page_indices ?? excludedPageIndices;
    const nextActivePage = overrides.active_page ?? visiblePageIndexRef.current;
    const savedSnapshot = buildSessionContentSnapshot(
      pages.length,
      nextCrop,
      nextCropConfirmed,
      nextColumnLayout,
      nextExcludedPageIndices,
      nextSelections,
    );
    const operation = async () => {
      setSaveState("saving");
      try {
        const session = await updateBatchSession(sessionHash, sessionRevisionRef.current, {
        page_count: pages.length,
        active_page: nextActivePage,
        crop_rect: nextCrop,
        crop_confirmed: nextCropConfirmed,
        column_layout: {
          column_count: nextColumnLayout.columnCount,
          overlap_ratio: nextColumnLayout.overlapRatio,
        },
        excluded_page_indices: nextExcludedPageIndices,
        segments: selectionsToSessionSegments(nextSelections),
      });
      const { snapshot: confirmedSnapshot } = applyServerSession(session, false);
      if (confirmedSnapshot !== savedSnapshot) {
        throw new Error("后端返回的批量扫描保存结果与请求不一致");
      }
      setSaveState(currentContentSnapshotRef.current === savedSnapshot ? "saved" : "idle");
      return session;
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 409) {
          const latest = await getBatchSession(sessionHash);
          if (latest) {
            applyServerSession(latest, true);
            setSaveState("saved");
            notify.error({ title: "批量扫描已在另一处修改，已加载最新版本" });
          }
          throw reason;
        }
        setSaveState("failed");
        throw reason;
      }
    };
    const queued = saveQueueRef.current.then(operation, operation);
    saveQueueRef.current = queued.then(() => undefined, () => undefined);
    return queued;
  }, [applyServerSession, columnLayout, crop, cropConfirmed, excludedPageIndices, pages.length, sessionHash]);

  useEffect(() => {
    if (!sessionHash || !pages.length || contentSnapshot === persistedContentSnapshotRef.current) return;
    const timer = window.setTimeout(() => {
      if (submissionRef.current) return;
      if (currentContentSnapshotRef.current === persistedContentSnapshotRef.current) return;
      void persistSession().catch(() => undefined);
    }, 650);
    return () => window.clearTimeout(timer);
  }, [contentSnapshot, pages.length, persistSession, sessionHash]);

  useEffect(() => {
    if (saveState !== "failed" || !sessionHash) return;
    const timer = window.setTimeout(() => {
      if (submissionRef.current) return;
      void persistSession().catch(() => undefined);
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [persistSession, saveState, sessionHash]);

  useEffect(() => {
    if (!selections.some((selection) => selection.status === "processing") || !currentSession) return;
    const timer = window.setInterval(() => {
      void getBatchSession(currentSession.file_hash).then((session) => {
        if (!session) return;
        applyServerSession(session, true);
        setSaveState("saved");
      }).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [applyServerSession, currentSession, selections]);

  const goToPage = useCallback((pageIndex: number) => {
    const requested = clamp(pageIndex, 0, Math.max(0, pages.length - 1));
    const target = nearestAvailablePageIndex(pages, excludedPageIndices, requested);
    setActivePageIndex(target);
    setVisiblePageIndex(target);
    setPageInput(String(target + 1));
    loadPage(target);
    if (cropConfirmed || cropView === "preview") {
      const page = viewportRef.current?.querySelector<HTMLElement>(`[data-page-index="${target}"]`);
      page?.scrollIntoView({ block: "start" });
    }
  }, [cropConfirmed, cropView, excludedPageIndices, loadPage, pages]);

  const updateSelections = useCallback((next: SelectionModel[]) => {
    setSelections(sortAndNumber(next));
  }, []);

  const reprojectSelections = useCallback((items: SelectionModel[], nextExcludedPageIndices: number[]) => {
    const excluded = new Set(nextExcludedPageIndices);
    const nextMetrics = buildPageMetrics(
      pages.filter((page) => !excluded.has(page.pageIndex)),
      crop,
      columnLayout,
    );
    return sortAndNumber(items.flatMap((selection) => {
      const rect = documentRectFromSlices(selection.slices, nextMetrics);
      if (!rect) return [];
      return [{
        ...selection,
        rect,
        start: { x: rect.left, y: rect.top },
        end: { x: rect.right, y: rect.bottom },
      }];
    }));
  }, [columnLayout, crop, pages]);

  const focusPageAfterLayoutChange = useCallback((pageIndex: number) => {
    setActivePageIndex(pageIndex);
    setVisiblePageIndex(pageIndex);
    setPageInput(String(pageIndex + 1));
    loadPage(pageIndex);
    window.requestAnimationFrame(() => {
      viewportRef.current?.querySelector<HTMLElement>(`[data-page-index="${pageIndex}"]`)?.scrollIntoView({ block: "start" });
    });
  }, [loadPage]);

  const deletePage = useCallback((pageIndex: number) => {
    if (activePages.length <= 1) {
      notify.error({ title: "至少保留一页" });
      return;
    }
    const affected = selectionsRef.current.filter((selection) => selection.slices.some((slice) => slice.pageIndex === pageIndex));
    if (affected.some((selection) => selection.status !== "pending")) {
      notify.error({ title: "该页已有已提交题目，不能删除" });
      return;
    }
    const nextExcluded = [...new Set([...excludedPageIndices, pageIndex])].sort((a, b) => a - b);
    const removedIds = new Set(affected.map((selection) => selection.id));
    const nextSelections = reprojectSelections(
      selectionsRef.current.filter((selection) => !removedIds.has(selection.id)),
      nextExcluded,
    );
    selectionsRef.current = nextSelections;
    setSelections(nextSelections);
    if (activeSelectionId && removedIds.has(activeSelectionId)) setActiveSelectionId(undefined);
    setExcludedPageIndices(nextExcluded);
    const target = nearestAvailablePageIndex(pages, nextExcluded, pageIndex);
    focusPageAfterLayoutChange(target);
    void persistSession(nextSelections, { excluded_page_indices: nextExcluded, active_page: target }).catch(() => undefined);
    notify.success({
      title: affected.length
        ? `第 ${pageIndex + 1} 页已删除，同时移除 ${affected.length} 个待提交选框`
        : `第 ${pageIndex + 1} 页已删除，可在页面栏恢复`,
    });
  }, [activePages.length, activeSelectionId, excludedPageIndices, focusPageAfterLayoutChange, pages, persistSession, reprojectSelections]);

  const restorePage = useCallback((pageIndex: number) => {
    const bridging = selectionsRef.current.filter((selection) => {
      const pageIndices = selection.slices.map((slice) => slice.pageIndex);
      return pageIndices.length > 1 && Math.min(...pageIndices) < pageIndex && pageIndex < Math.max(...pageIndices);
    });
    if (bridging.some((selection) => selection.status !== "pending")) {
      notify.error({ title: "已有已提交题目跨过该位置，不能恢复页面" });
      return;
    }
    const applyRestore = () => {
      const nextExcluded = excludedPageIndices.filter((index) => index !== pageIndex);
      const removedIds = new Set(bridging.map((selection) => selection.id));
      const nextSelections = reprojectSelections(
        selectionsRef.current.filter((selection) => !removedIds.has(selection.id)),
        nextExcluded,
      );
      selectionsRef.current = nextSelections;
      setSelections(nextSelections);
      if (activeSelectionId && removedIds.has(activeSelectionId)) setActiveSelectionId(undefined);
      setExcludedPageIndices(nextExcluded);
      focusPageAfterLayoutChange(pageIndex);
      void persistSession(nextSelections, { excluded_page_indices: nextExcluded, active_page: pageIndex }).catch(() => undefined);
    };
    if (bridging.length) {
      confirmAction({
        title: "恢复页面",
        message: `恢复第 ${pageIndex + 1} 页会删除跨过该位置的 ${bridging.length} 个待提交选框，是否继续？`,
        confirmLabel: "恢复",
        destructive: true,
        onConfirm: applyRestore,
      });
      return;
    }
    applyRestore();
  }, [activeSelectionId, excludedPageIndices, focusPageAfterLayoutChange, persistSession, reprojectSelections]);

  const deleteActiveSelection = useCallback(() => {
    if (!activeSelection || activeSelection.status !== "pending") return;
    updateSelections(selectionsRef.current.filter((selection) => selection.id !== activeSelection.id));
    setActiveSelectionId(undefined);
  }, [activeSelection, updateSelections]);

  const submitPending = useCallback(async () => {
    if (!currentSession || isSubmitting) return;
    const pending = selectionsRef.current.filter((selection) => selection.status === "pending");
    if (!pending.length) return;
    submissionRef.current = true;
    setIsSubmitting(true);
    try {
      await persistSession(selectionsRef.current);
      const result = await processBatchSession(
        currentSession.file_hash,
        sessionRevisionRef.current,
      );
      applyServerSession(result.session, true);
      setSaveState("saved");
      if (result.failed) {
        notify.error({ title: `${result.queued}/${result.requested} 道已入队，${result.failed} 道失败` });
      } else {
        notify.success({ title: `${result.queued}/${result.requested} 道题目已由后端统一入队` });
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "批量启动失败";
      notify.error({ title: message });
    } finally {
      submissionRef.current = false;
      setIsSubmitting(false);
    }
  }, [applyServerSession, currentSession, isSubmitting, persistSession]);

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
  return (
    <Box className={`batch-scan-page${pages.length ? " is-active" : ""}`}>
      <RenameDialog
        opened={renameTarget !== null}
        title="重命名最近文件"
        label="文件名"
        value={renameValue}
        onChange={setRenameValue}
        onCancel={() => setRenameTarget(null)}
        onConfirm={renameSession}
        loading={isRenaming}
      />
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
          <BatchSessionHistory
            sessions={savedSessions}
            isImporting={isImporting}
            onRename={openRenameSession}
            onResume={(session) => void resumeSession(session)}
            onDelete={(session) => confirmAction({
              title: "删除批量扫描记录",
              message: "已生成的任务和题目会保留。此操作无法撤销。",
              confirmLabel: "删除",
              destructive: true,
              onConfirm: async () => {
                await deleteBatchSession(session.file_hash);
                await refreshSavedSessions();
              },
            })}
          />
        </>
      ) : (
        <>
          <Box className="batch-workflow-toolbar">
            <IconButton icon={ArrowLeft} variant="invisible" aria-label="返回最近文件" title="返回最近文件" onClick={clearWorkspace} />
            <IconButton icon={PanelLeft} variant={leftOpen ? "default" : "invisible"} aria-label="切换页面栏" title="切换页面栏" onClick={() => setLeftOpen((value) => !value)} />
            <IconButton icon={PanelRight} variant={rightOpen ? "default" : "invisible"} aria-label="切换选框栏" title="切换选框栏" onClick={() => setRightOpen((value) => !value)} />
            {sessionHash && (
              <span className={`batch-save-state is-${saveState}`}>
                {saveState === "saving" ? "正在保存" : saveState === "failed" ? "保存失败，正在重试" : saveState === "saved" ? "已保存" : "尚未修改"}
              </span>
            )}
            {!cropConfirmed && (
              <label className="batch-column-count">
                <span>分栏</span>
                <select
                  aria-label="分栏数量"
                  value={columnLayout.columnCount}
                  onChange={(event) => setColumnLayout({ columnCount: Number(event.target.value), overlapRatio: 0.5 })}
                >
                  <option value={1}>不分栏</option>
                  {[2, 3, 4, 5, 6].map((count) => <option key={count} value={count}>{count} 栏</option>)}
                </select>
              </label>
            )}
            <span className="batch-workflow-toolbar__spacer" />
            <IconButton
              icon={Contrast}
              variant={inverted ? "default" : "invisible"}
              aria-label="切换 PDF 暗色预览"
              aria-pressed={inverted}
              title="切换 PDF 暗色预览"
              onClick={() => setInverted((value) => !value)}
            />
            {cropConfirmed && (
              <>
                <IconButton icon={Trash2} variant="invisible" aria-label="删除当前选框" title="删除当前选框" disabled={!activeSelection || activeSelection.status !== "pending"} onClick={deleteActiveSelection} />
                <Button variant="primary" disabled={!pendingCount || isSubmitting} onClick={() => void submitPending()}>
                  {isSubmitting ? "正在提交" : `提交 ${pendingCount} 道题目`}
                </Button>
              </>
            )}
            {!cropConfirmed && cropView === "edit" && <Button variant="default" disabled={cropTooSmall} onClick={() => setCropView("preview")}>检查裁剪与分栏</Button>}
            {!cropConfirmed && cropView === "preview" && <Button variant="default" onClick={() => setCropView("edit")}>调整裁剪与分栏</Button>}
            {!cropConfirmed && cropView === "preview" && (
              <Button variant="primary" disabled={cropTooSmall} onClick={() => {
                setCropConfirmed(true);
                void persistSession([], { crop_rect: crop, crop_confirmed: true }).catch(() => undefined);
              }}><Check size={16} />确认裁剪与分栏并开始框题</Button>
            )}
          </Box>

          <Box className={`batch-continuous-workspace${leftOpen ? " has-left" : ""}${rightOpen && cropConfirmed ? " has-right" : ""}`}>
            {leftOpen && (
              <aside className="batch-page-rail" aria-label="页面导航">
                <Text className="batch-rail-title">页面</Text>
                <nav>{pages.map((page) => {
                  const excluded = excludedPageSet.has(page.pageIndex);
                  const active = !excluded && (renderDocument ? visiblePageIndex : activePageIndex) === page.pageIndex;
                  return (
                    <div key={page.id} className={`batch-page-rail__item${active ? " is-active" : ""}${excluded ? " is-excluded" : ""}`}>
                      <button
                        type="button"
                        className="batch-page-rail__page"
                        aria-label={`第 ${page.pageIndex + 1} 页${excluded ? "，已删除" : ""}`}
                        aria-current={active ? "page" : undefined}
                        disabled={excluded}
                        onClick={() => goToPage(page.pageIndex)}
                      >
                        <span>{page.pageIndex + 1}</span>
                        {excluded && <small>已删除</small>}
                      </button>
                      <button
                        type="button"
                        className="batch-page-rail__action"
                        aria-label={excluded ? `恢复第 ${page.pageIndex + 1} 页` : `删除第 ${page.pageIndex + 1} 页`}
                        title={excluded ? "恢复页面" : "删除页面"}
                        disabled={!excluded && activePages.length <= 1}
                        onClick={() => excluded ? restorePage(page.pageIndex) : deletePage(page.pageIndex)}
                      >
                        {excluded ? <RefreshCw size={14} /> : <Trash2 size={14} />}
                      </button>
                    </div>
                  );
                })}</nav>
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
                    pages={activePages}
                    crop={crop}
                    columnLayout={columnLayout}
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
                  <ImageSelectionStage
                    src={imageUrls[activePageIndex]}
                    alt={pages[activePageIndex].label}
                    layout="fixed"
                    tone={inverted ? "inverted" : "original"}
                    fallback={<Spinner />}
                    style={{ width: `${Math.round(820 * zoom)}px`, aspectRatio: `${pages[activePageIndex].sourceWidth} / ${pages[activePageIndex].sourceHeight}` }}
                  >
                    <NormalizedRectEditor
                      value={crop}
                      verticalGuides={columnLayout.columnCount}
                      onChange={setCrop}
                      onTooSmall={() => notify.error({ title: `裁剪区域过小，宽高至少为页面的 ${Math.round(MIN_CROP_SIZE * 100)}%` })}
                    />
                  </ImageSelectionStage>
                )}
              </div>
            </main>

            {rightOpen && cropConfirmed && (
              <BatchSelectionRail
                selections={selections}
                activeSelectionId={activeSelectionId}
                columnCount={columnLayout.columnCount}
                onActivate={(selection) => {
                  setActiveSelectionId(selection.id);
                  const y = selection.rect.top / Math.max(1, metrics.at(-1)?.documentBottom ?? 1);
                  if (viewportRef.current) viewportRef.current.scrollTop = y * viewportRef.current.scrollHeight - 80;
                }}
                onReview={(selection, reason) => void markSelectionReview(selection, reason)}
                onRetry={(selection) => void retrySelection(selection)}
              />
            )}
          </Box>
        </>
      )}

    </Box>
  );
}
