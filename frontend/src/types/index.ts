import type { Tier } from "@/lib/tiers";

// User types
export interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  theme: "minimal" | "professional" | "bold";
  created_at: string;
}

export interface UserProfileUpdate {
  name?: string;
  theme?: "minimal" | "professional" | "bold";
}

// CV types
export interface CV {
  id: string;
  name: string;
  original_filename: string;
  content_text?: string | null;
  created_at: string;
}

export interface CVListResponse {
  cvs: CV[];
}

// Optimization types
export interface OptimizeRequest {
  cv_id: string;
  job_input: string;
  max_iterations?: number;
  parallel?: boolean;
}

export interface JobParsed {
  title: string;
  company: string;
  location?: string;
  requirements: string[];
  responsibilities: string[];
  keywords: string[];
}

export interface FilterResult {
  filter_name: string;
  passed: boolean;
  score: number;
  threshold: number;
  issues: string[];
  suggestions: string[];
}

export interface IterationFeedback {
  iteration: number;
  passed: boolean;
  results: FilterResult[];
}

export interface OptimizationStatus {
  id: string;
  status:
    | "pending"
    | "parse_job"
    | "generate"
    | "validate"
    | "refine"
    | "complete"
    | "failed";
  current_step: string | null;
  iterations: number;
  job_parsed: JobParsed | null;
  job_url: string | null;
  feedback: IterationFeedback[] | null;
  result_html: string | null;
  error: string | null;
  created_at: string;
}

export interface OptimizationStartResponse {
  run_id: string;
  status: string;
}

export interface OptimizationSummary {
  id: string;
  status: string;
  job_title: string | null;
  job_company: string | null;
  job_url: string | null;
  created_at: string;
}

export interface OptimizationListResponse {
  runs: OptimizationSummary[];
}

// Editor types
export interface ResumePatch {
  selector: string;
  action: "replace" | "append" | "prepend" | "remove";
  html: string | null;
}

export interface EditResponse {
  patches: ResumePatch[];
  updated_html: string;
}

export interface RequirementItem {
  id: string;
  text: string;
  covered: boolean;
}

export interface RequirementsResponse {
  requirements: RequirementItem[];
}

export interface ValidateResponse {
  results: FilterResult[];
  requirements: RequirementItem[];
}

// Theme type
export type Theme = "minimal" | "professional" | "bold";

// Subscription types
export interface SubscriptionStatus {
  tier: Tier;
  status: "none" | "active" | "cancelled";
  remaining: number | null;
  is_unlimited: boolean;
  weekly_reset_at: string | null;
  current_period_end: string | null;
}

export interface CheckoutResponse {
  checkout_url: string;
}

// Coach types
export interface CoachSession {
  id: string;
  optimization_run_id: string;
  title: string | null;
  last_message_at: string | null;
  message_count: number;
  preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoachMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CoachChatRequest {
  message: string;
  thread_id?: string;
  optimization_run_id?: string;
}

export interface CoachSSEEvent {
  type: "delta" | "done" | "error";
  content?: string;
  thread_id?: string;
}

// Storybank types
export interface StorybankEntry {
  id: string;
  title: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  tags: string[];
  rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface StorybankEntryRequest {
  title: string;
  situation?: string;
  task?: string;
  action?: string;
  result?: string;
  tags?: string[];
  rating?: number | null;
}

export type FeedbackType = "refund" | "bug" | "idea";

export interface FeedbackRequest {
  type: FeedbackType;
  message: string;
}

export interface FeedbackResponse {
  ok: boolean;
}
