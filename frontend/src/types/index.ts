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
  status: "trial" | "active" | "cancelled" | "expired";
  remaining_requests: number | null;
  is_unlimited: boolean;
  is_trial: boolean;
  can_subscribe: boolean;
  can_buy_addon: boolean;
  renewal_date: string | null;
}

export interface CheckoutRequest {
  success_url: string;
  cancel_url: string;
}

export interface CheckoutResponse {
  checkout_url: string;
}
