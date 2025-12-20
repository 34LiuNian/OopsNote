export interface TaskResponse {
  task: {
    id: string;
    status: string;
    stage?: string | null;
    stage_message?: string | null;
    asset?: {
      asset_id: string;
      source: string;
      original_reference?: string | null;
      path?: string | null;
      mime_type?: string | null;
      size_bytes?: number | null;
    } | null;
    problems: Array<{
      problem_id: string;
      question_no?: string | null;
      source?: string | null;
      knowledge_tags?: string[];
      error_tags?: string[];
      user_tags?: string[];
      problem_text: string;
      latex_blocks?: string[];
      options?: Array<{
        key: string;
        text: string;
        latex_blocks?: string[];
      }>;
    }>;
    solutions: Array<{
      problem_id: string;
      answer: string;
      explanation: string;
    }>;
    tags: Array<{
      problem_id: string;
      knowledge_points: string[];
    }>;
  };
}

export interface TaskSummary {
  id: string;
  status: string;
  stage?: string | null;
  stage_message?: string | null;
  created_at: string;
  updated_at: string;
  subject: string;
  question_no?: string | null;
}

export interface TasksResponse {
  items: TaskSummary[];
}

export interface ProblemSummary {
  task_id: string;
  problem_id: string;
  question_no?: string | null;
  subject: string;
  grade?: string | null;
  source?: string | null;
  knowledge_points: string[];
  knowledge_tags?: string[];
  error_tags?: string[];
  user_tags?: string[];
}

export interface ProblemsResponse {
  items: ProblemSummary[];
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

export type TagDimension = "knowledge" | "error" | "meta" | "custom";

export interface TagItem {
  id: string;
  dimension: TagDimension;
  value: string;
  aliases?: string[];
  created_at: string;
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
