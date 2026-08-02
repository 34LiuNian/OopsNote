export type TaskStatus = "pending" | "processing" | "completed" | "failed" | "cancelled";
export type TaskStage = "queued" | "starting" | "ocr" | "solving" | "verifying" | "tagging" | "finalizing" | "syncing";
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "timed_out";
export type ContentFormat = "legacy-markdown-latex" | "oopsmark-v1";
export type NormalizedRect = { x: number; y: number; width: number; height: number };
export type DiagramImageTone = "auto" | "original";

export interface TaskRunSummary {
  id: string;
  attempt: number;
  status: RunStatus;
  pid?: number | null;
  exit_code?: number | null;
  log_path?: string | null;
  prompt_version: string;
  duration_ms?: number | null;
  started_at?: string | null;
  heartbeat_at: string;
  ended_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  stages: Array<{
    stage: TaskStage;
    status: "running" | "completed" | "failed" | "cancelled";
    started_at: string;
    ended_at?: string | null;
    message?: string | null;
    error_code?: string | null;
    latency_ms?: number | null;
  }>;
}

export interface SourceTrace {
  kind: "single_image" | "batch_segment";
  screenshot_path: string;
  screenshot_filename?: string;
  source_file_hash?: string;
  source_file_name?: string;
  source_file_path?: string;
  page_index?: number;
  question_no?: number;
  segment_id?: string;
  batch_session_available?: boolean;
}

export interface TaskResponse {
  task: {
    id: string;
    status: TaskStatus;
    stage?: TaskStage | null;
    stage_message?: string | null;
    active_run_id?: string | null;
    run?: TaskRunSummary | null;
    created_at: string;
    updated_at: string;
    asset?: {
      asset_id: string;
      source: string;
      original_reference?: string | null;
      path?: string | null;
      mime_type?: string | null;
      size_bytes?: number | null;
    } | null;
    payload?: {
      difficulty?: string | null;
    } | null;
    trace?: SourceTrace | null;
    problem: {
      problem_id: string;
      question_no?: string | null;
      question_type?: string | null;
      source?: string | null;
      difficulty?: string | null;
      has_diagram?: boolean;
      diagram_detected?: boolean;
      diagram_kind?: string | null;
      diagram_tikz_source?: string | null;
      diagram_svg?: string | null;
      diagram_image_path?: string | null;
      diagram_image_crop?: NormalizedRect | null;
      diagram_image_tone?: DiagramImageTone;
      diagram_position?: "left" | "right";
      diagram_scale_percent?: number | null;
      diagram_render_status?: string | null;
      diagram_error?: string | null;
      diagram_needs_review?: boolean;
      diagram_confidence?: number | null;
      knowledge_tags?: string[];
      error_tags?: string[];
      user_tags?: string[];
      trace?: SourceTrace | null;
      content_format?: ContentFormat;
      problem_text: string;
      options?: Array<{
        key: string;
        text: string;
      }>;
    } | null;
    solution: {
      problem_id: string;
      answer: string;
      short_answer?: string;
      explanation: string;
    } | null;
    tag: {
      problem_id: string;
      knowledge_points: string[];
    } | null;
    merged_into?: {
      task_id: string;
      problem_id: string;
    } | null;
  };
}

export interface TaskSummary {
  id: string;
  status: TaskStatus;
  stage?: TaskStage | null;
  stage_message?: string | null;
  active_run_id?: string | null;
  created_at: string;
  updated_at: string;
  subject: string;
  question_no?: string | null;
  asset?: {
    asset_id: string;
    path: string;
    mime_type?: string | null;
  } | null;
}

export interface TasksResponse {
  items: TaskSummary[];
}

export interface ProblemSummary {
  task_id: string;
  problem_id: string;
  question_no?: string | null;
  question_type?: string | null;
  content_format?: ContentFormat;
  problem_text: string;
  options?: Array<{
    key: string;
    text: string;
  }>;
  subject: string;
  grade?: string | null;
  source?: string | null;
  difficulty?: string | null;
  has_diagram?: boolean;
  diagram_detected?: boolean;
  diagram_kind?: "tikz" | "image" | null;
  diagram_tikz_source?: string | null;
  diagram_svg?: string | null;
  diagram_image_path?: string | null;
  diagram_image_crop?: NormalizedRect | null;
  diagram_image_tone?: DiagramImageTone;
  diagram_position?: "left" | "right";
  diagram_scale_percent?: number | null;
  diagram_render_status?: string | null;
  diagram_error?: string | null;
  diagram_needs_review?: boolean;
  knowledge_points: string[];
  knowledge_tags?: string[];
  error_tags?: string[];
  user_tags?: string[];
  trace?: SourceTrace | null;
  created_at: string;
}

export interface ProblemsResponse {
  items: ProblemSummary[];
}

export interface KnowledgeTreeNode {
  id: string;
  source_id?: string | null;
  parent_id?: string | null;
  title: string;
  depth: number;
  scope?: string | null;
  selectable: boolean;
  is_leaf: boolean;
  children: KnowledgeTreeNode[];
}

export interface KnowledgeTreeResponse {
  schema_version: string;
  subjects: Record<string, {
    subject: string;
    subject_label: string;
    root: KnowledgeTreeNode;
  }>;
}

export type DifficultyBand = "easy" | "medium" | "hard";

export interface PaperDraftItem {
  id: string;
  task_id: string;
  problem_id: string;
  question_type: string;
  difficulty_coefficient?: number | null;
  points?: number | null;
  answer_space: string;
  problem?: (ProblemSummary & { difficulty_coefficient?: number | null }) | null;
}

export interface PaperDraft {
  id: string;
  title: string;
  subject: string;
  knowledge_tags: string[];
  knowledge_node_ids: string[];
  difficulty_preset: string;
  difficulty_distribution: Record<DifficultyBand, number>;
  requested_counts: Record<string, number>;
  items: PaperDraftItem[];
  created_at: string;
  updated_at: string;
}

export interface PaperDraftResponse {
  paper: PaperDraft;
}

export interface PaperDraftsResponse {
  items: PaperDraft[];
}

export interface ModelSummary {
  id: string;
  provider?: string | null;
  provider_type?: string | null;
}

export interface ModelsResponse {
  items: ModelSummary[];
}

export interface AgentModelsResponse {
  models: Record<string, string>;
}

export interface AgentModelsUpdateRequest {
  models: Record<string, string>;
}

export interface AgentEnabledResponse {
  enabled: Record<string, boolean>;
}

export interface AgentEnabledUpdateRequest {
  enabled: Record<string, boolean>;
}

export interface AgentThinkingResponse {
  thinking: Record<string, boolean>;
}

export interface AgentThinkingUpdateRequest {
  thinking: Record<string, boolean>;
}

// ── Agent Temperature ────────────────────────────────────────────────────

export interface AgentTemperatureResponse {
  temperature: Record<string, number>;
}

export interface AgentTemperatureUpdateRequest {
  temperature: Record<string, number>;
}

// ── Gateway Settings ─────────────────────────────────────────────────────

export interface GatewaySettingsResponse {
  base_url: string | null;
  api_key_masked: string | null;
  has_api_key: boolean;
  default_model: string | null;
  temperature: number | null;
  env_base_url: string | null;
  env_has_api_key: boolean;
  env_default_model: string | null;
  env_temperature: number | null;
}

export interface GatewaySettingsUpdateRequest {
  base_url?: string | null;
  api_key?: string | null;
  default_model?: string | null;
  temperature?: number | null;
}

export interface GatewayTestRequest {
  base_url: string;
  api_key?: string | null;
}

export interface GatewayTestResponse {
  success: boolean;
  message: string;
  models_count: number;
}

// ── Debug Settings ───────────────────────────────────────────────────────

export interface DebugSettingsResponse {
  debug_llm_payload: boolean;
  persist_tasks: boolean;
}

export interface DebugSettingsUpdateRequest {
  debug_llm_payload?: boolean;
  persist_tasks?: boolean;
}

// ── System Info ──────────────────────────────────────────────────────────

export interface SystemInfoResponse {
  gateway_reachable: boolean | null;
  gateway_url: string | null;
  storage_path: string;
  env_configured: boolean;
  models_count: number;
}

export type TagDimension = "knowledge" | "error" | "meta" | "custom";

export interface TagItem {
  id: string;
  dimension: TagDimension;
  value: string;
  aliases?: string[];
  subject?: string | null;
  chapter?: string | null;
  source?: "builtin" | "user";
  ref_count?: number;
}

export interface TagsResponse {
  items: TagItem[];
}

export interface TagDimensionStyle {
  label: string;
  label_variant: string;
}

export interface TagDimensionsResponse {
  dimensions: Record<string, TagDimensionStyle>;
}

export interface TagDimensionsUpdateRequest {
  dimensions: Record<string, TagDimensionStyle>;
}

export interface PiSettingsResponse {
  pi_concurrency: number;
  workers: number;
  applies_on_restart: boolean;
}

export interface PiSettingsUpdateRequest {
  pi_concurrency: number;
}
