import { getSupabaseClient } from "./supabase";
import type {
  CV,
  CVListResponse,
  OptimizationStartResponse,
  OptimizationStatus,
  OptimizeRequest,
  UserProfile,
  UserProfileUpdate,
  SubscriptionStatus,
  CheckoutResponse,
} from "@/types";

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
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed: ${response.status}`);
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

// Subscription API
export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  return fetchWithAuth<SubscriptionStatus>("/subscription");
}

export async function createSubscriptionCheckout(
  successUrl: string,
  cancelUrl: string
): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/checkout/subscription", {
    method: "POST",
    body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function createAddonCheckout(
  successUrl: string,
  cancelUrl: string
): Promise<CheckoutResponse> {
  return fetchWithAuth<CheckoutResponse>("/subscription/checkout/addon", {
    method: "POST",
    body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
  });
}
