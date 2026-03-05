// ── API response types matching FastAPI backend ──

export interface DashboardStats {
  calls_today: number;
  total_farmers: number;
  avg_duration_seconds: number;
  active_calls: number;
}

export interface Call {
  call_sid: string;
  phone: string;
  direction: string;
  status: string;
  duration_seconds: number | null;
  language_detected: string | null;
  tools_used: string | null;
  state: string;
  district: string;
  created_at: string | null;
  ended_at: string | null;
}

export interface CallsResponse {
  calls: Call[];
  total: number;
  page: number;
  per_page: number;
}

export interface UserProfile {
  phone: string;
  name: string | null;
  state: string | null;
  district: string | null;
  language: string | null;
  crops: string | null;
  land_acres: number | null;
  call_count: number;
  created_at: string | null;
}

export interface UsersResponse {
  users: UserProfile[];
  total: number;
  page: number;
  per_page: number;
}

export interface LanguageDistribution {
  language: string;
  count: number;
}

export interface ToolUsage {
  tool: string;
  count: number;
}

export interface VolumePoint {
  date: string;
  calls: number;
}

export interface AnalyticsData {
  language_distribution: LanguageDistribution[];
  tool_usage: ToolUsage[];
  call_volume_7d: VolumePoint[];
  call_volume_30d: VolumePoint[];
  total_calls_month: number;
  languages_active: number;
  new_farmers_month: number;
  top_states: string[];
}

export interface ConversationTurn {
  turn_number: number;
  speaker: string;
  transcript: string;
  tool_called: string | null;
  created_at: string | null;
}

export interface TranscriptResponse {
  turns: ConversationTurn[];
}

export interface TranslateResponse {
  translations: string[];
}

export interface HealthService {
  name: string;
  status: "healthy" | "degraded" | "down";
  latency_ms?: number;
}

export interface HealthData {
  status: string;
  service: string;
  services?: HealthService[];
  uptime_seconds?: number;
}
