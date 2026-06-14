import { getSupabaseClient } from "./supabase";
import type {
  CV,
  CVListResponse,
  CoachMessage,
  CoachSession,
  EditResponse,
  OptimizationListResponse,
  OptimizationStartResponse,
  OptimizationStatus,
  OptimizationSummary,
  OptimizeRequest,
  RequirementsResponse,
  FeedbackRequest,
  FeedbackResponse,
  UserProfile,
  UserProfileUpdate,
  SubscriptionStatus,
  CheckoutResponse,
  ValidateResponse,
} from "@/types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function getAuthHeaders(): Promise<HeadersInit> {
  const supabase = getSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("Not authenticated");
  }

  return {
    Authorization: `Bearer ${session.access_token}`,
  };
}

async function fetchWithAuth<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...headers,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    let message: string;
    if (typeof detail === "string") {
      message = detail;
    } else if (
      detail &&
      typeof detail === "object" &&
      typeof (detail as { reason?: unknown }).reason === "string"
    ) {
      message = (detail as { reason: string }).reason;
    } else {
      message = `Request failed: ${response.status}`;
    }
    throw new ApiError(message, response.status, detail);
  }

  return response.json();
}

// User API
export async function getProfile(): Promise<UserProfile> {
  return fetchWithAuth<UserProfile>("/me");
}

export async function updateProfile(
  updates: UserProfileUpdate
): Promise<UserProfile> {
  return fetchWithAuth<UserProfile>("/me", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

// CV API
export async function listCVs(): Promise<CV[]> {
  const response = await fetchWithAuth<CVListResponse>("/cvs");
  return response.cvs;
}

export async function getCV(cvId: string): Promise<CV> {
  return fetchWithAuth<CV>(`/cvs/${cvId}`);
}

export async function uploadCV(file: File, name?: string): Promise<CV> {
  const headers = await getAuthHeaders();
  const formData = new FormData();
  formData.append("file", file);
  if (name) {
    formData.append("name", name);
  }

  const response = await fetch(`${API_BASE}/cvs`, {
    method: "POST",
    headers: {
      Authorization: (headers as Record<string, string>).Authorization,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Upload failed: ${response.status}`);
  }

  return response.json();
}

export async function deleteCV(cvId: string): Promise<void> {
  await fetchWithAuth(`/cvs/${cvId}`, { method: "DELETE" });
}

// Optimization API
export async function listOptimizations(): Promise<OptimizationSummary[]> {
  const response = await fetchWithAuth<OptimizationListResponse>("/optimize");
  return response.runs;
}

export async function startOptimization(
  request: OptimizeRequest
): Promise<OptimizationStartResponse> {
  return fetchWithAuth<OptimizationStartResponse>("/optimize", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getOptimizationStatus(
  runId: string
): Promise<OptimizationStatus> {
  return fetchWithAuth<OptimizationStatus>(`/optimize/${runId}`);
}

export async function downloadOptimizationPDF(runId: string): Promise<Blob> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/optimize/${runId}/pdf`, {
    headers,
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  return response.blob();
}

export async function deleteOptimization(runId: string): Promise<void> {
  await fetchWithAuth(`/optimize/${runId}`, { method: "DELETE" });
}

export async function updateOptimizationJob(
  runId: string,
  patch: { title?: string; company?: string }
): Promise<OptimizationStatus> {
  return fetchWithAuth<OptimizationStatus>(`/optimize/${runId}/job`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

// Editor API
export async function getRequirements(
  runId: string
): Promise<RequirementsResponse> {
  return fetchWithAuth<RequirementsResponse>(
    `/optimize/${runId}/requirements`
  );
}

export async function editResume(
  runId: string,
  instruction: string,
  html: string
): Promise<EditResponse> {
  return fetchWithAuth<EditResponse>(`/optimize/${runId}/edit`, {
    method: "POST",
    body: JSON.stringify({ instruction, html }),
  });
}

export async function validateResume(
  runId: string,
  html: string
): Promise<ValidateResponse> {
  return fetchWithAuth<ValidateResponse>(`/optimize/${runId}/validate`, {
    method: "POST",
    body: JSON.stringify({ html }),
  });
}

export async function downloadPdfFromHtml(
  runId: string,
  html: string
): Promise<Blob> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/optimize/${runId}/download`, {
    method: "POST",
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ html }),
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  return response.blob();
}

// Subscription API
export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  return fetchWithAuth<SubscriptionStatus>("/subscription");
}

export async function createCheckout(
  tier: "job_hunter" | "offer_mode",
  successUrl: string,
  cancelUrl: string,
): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/checkout", {
    method: "POST",
    body: JSON.stringify({ tier, success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function createBillingPortal(returnUrl: string): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/billing-portal", {
    method: "POST",
    body: JSON.stringify({ return_url: returnUrl }),
  });
}

export interface UpgradePreview {
  amount_due: number; // cents
  currency: string;
}

export async function previewUpgrade(tier: string): Promise<UpgradePreview> {
  return fetchWithAuth<UpgradePreview>(`/subscription/upgrade-preview?tier=${tier}`);
}

export async function upgradeSubscription(tier: string): Promise<void> {
  await fetchWithAuth<void>("/subscription/upgrade", {
    method: "POST",
    body: JSON.stringify({ tier }),
  });
}

// Coach API
export async function listCoachSessions(): Promise<CoachSession[]> {
  return fetchWithAuth<CoachSession[]>("/coach/sessions");
}

export async function getCoachMessages(threadId: string): Promise<CoachMessage[]> {
  return fetchWithAuth<CoachMessage[]>(`/coach/sessions/${threadId}/messages`);
}

export async function createCoachThread(
  optimizationRunId: string,
): Promise<CoachSession> {
  return fetchWithAuth<CoachSession>("/coach/sessions", {
    method: "POST",
    body: JSON.stringify({ optimization_run_id: optimizationRunId }),
  });
}

export async function renameCoachThread(
  threadId: string,
  title: string | null,
): Promise<CoachSession> {
  return fetchWithAuth<CoachSession>(`/coach/sessions/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteCoachThread(threadId: string): Promise<void> {
  await fetchWithAuth(`/coach/sessions/${threadId}`, { method: "DELETE" });
}

export async function streamCoachChat(
  args: { threadId: string } | { optimizationRunId: string },
  message: string,
  onDelta: (text: string) => void = () => {},
  onDone: (threadId: string) => void = () => {},
  onError: (error: string) => void = () => {},
): Promise<void> {
  const headers = await getAuthHeaders();
  const body: Record<string, unknown> = { message };
  if ("threadId" in args) body.thread_id = args.threadId;
  else body.optimization_run_id = args.optimizationRunId;

  const response = await fetch(`${API_BASE}/coach/chat`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error?.detail;
    const message =
      typeof detail === "string" ? detail : `Chat failed: ${response.status}`;
    throw new ApiError(message, response.status, detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.type === "delta") onDelta(event.content || "");
        else if (event.type === "done") onDone(event.thread_id || "");
        else if (event.type === "error") onError(event.content || "Unknown error");
      } catch {
        /* skip malformed events */
      }
    }
  }
}

// Telegram API
export async function linkTelegramId(telegramId: number): Promise<void> {
  await fetchWithAuth("/auth/telegram/link", {
    method: "POST",
    body: JSON.stringify({ telegram_id: telegramId }),
  });
}

export async function exchangeTelegramInitData(
  initData: string
): Promise<{ token_hash: string; email: string }> {
  const response = await fetch(`${API_BASE}/auth/telegram/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : `Exchange failed: ${response.status}`,
      response.status,
      body?.detail,
    );
  }
  return response.json();
}

// Feedback API
export async function submitFeedback(
  body: FeedbackRequest,
): Promise<FeedbackResponse> {
  return fetchWithAuth<FeedbackResponse>("/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
