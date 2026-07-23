export type NormalizedRect = { x: number; y: number; width: number; height: number };

export type DocumentPoint = { x: number; y: number };

export type DocumentRect = { left: number; top: number; right: number; bottom: number };

export type DocumentCropRect = NormalizedRect;

export type ContinuousPageSource = {
  id: string;
  pageIndex: number;
  label: string;
  sourceWidth: number;
  sourceHeight: number;
};

export type PageMetric = ContinuousPageSource & {
  crop: DocumentCropRect;
  croppedSourceWidth: number;
  croppedSourceHeight: number;
  documentTop: number;
  documentBottom: number;
  displayWidth: number;
  displayHeight: number;
};

export type SelectionSlice = {
  pageId: string;
  pageIndex: number;
  rect: NormalizedRect;
  order: number;
};

export type SelectionStatus = "pending" | "processing" | "completed" | "failed";

export type SelectionModel = {
  id: string;
  start: DocumentPoint;
  end: DocumentPoint;
  rect: DocumentRect;
  slices: SelectionSlice[];
  questionNo: number;
  status: SelectionStatus;
  taskId?: string;
  problemIds?: string[];
  error?: string;
};

export type ResizeHandle = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";
