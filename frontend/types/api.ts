export interface TaskResponse {
  task: {
    id: string;
    status: string;
    stage?: string | null;
    stage_message?: string | null;
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
    problems: Array<{
      problem_id: string;
      question_no?: string | null;
      question_type?: string | null;
      source?: string | null;
      knowledge_tags?: string[];
      error_tags?: string[];
      user_tags?: string[];
      problem_text: string;
      options?: Array<{
        key: string;
        text: string;
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
  problem_text: string;
  options?: Array<{
    key: string;
    text: string;
  }>;
  subject: string;
  grade?: string | null;
  source?: string | null;
  knowledge_points: string[];
  knowledge_tags?: string[];
  error_tags?: string[];
  user_tags?: string[];
  created_at: string;
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

export type UserRole = "admin" | "member";

export interface UserPublic {
  username: string;
  role: UserRole;
  nickname?: string | null;
  avatar_url?: string | null;
  is_active?: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  nickname?: string;
  avatar_url?: string;
}

export interface UserProfileUpdateRequest {
  username?: string;
  nickname?: string;
  avatar_url?: string;
}

export interface PasswordUpdateRequest {
  current_password: string;
  new_password: string;
}

export interface AdminPasswordResetRequest {
  new_password: string;
}

export interface AdminUserUpdateRequest {
  role?: UserRole;
  is_active?: boolean;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
  user: UserPublic;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthMeResponse {
  user: UserPublic;
}

export interface UserListResponse {
  items: UserPublic[];
}

export interface RegistrationSettingsResponse {
  enabled: boolean;
}

export interface RegistrationSettingsUpdateRequest {
  enabled: boolean;
}
