import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "./api";
import type {
  DashboardStats,
  CallsResponse,
  UsersResponse,
  AnalyticsData,
  HealthData,
  TranscriptResponse,
  TranslateResponse,
} from "./types";

export function useStats() {
  return useQuery<DashboardStats>({
    queryKey: ["stats"],
    queryFn: () => apiFetch("/api/dashboard/stats"),
    refetchInterval: 10_000,
  });
}

export function useCalls(params: {
  page?: number;
  per_page?: number;
  language?: string;
  state?: string;
  status?: string;
  phone?: string;
}) {
  return useQuery<CallsResponse>({
    queryKey: ["calls", params],
    queryFn: () =>
      apiFetch("/api/dashboard/calls", params as Record<string, string | number>),
  });
}

export function useActiveCalls() {
  return useQuery<CallsResponse>({
    queryKey: ["active-calls"],
    queryFn: () => apiFetch("/api/dashboard/calls", { status: "in-progress", per_page: 50 }),
    refetchInterval: 3_000,
  });
}

export function useUsers(params: {
  page?: number;
  per_page?: number;
  phone?: string;
  state?: string;
  crop?: string;
}) {
  return useQuery<UsersResponse>({
    queryKey: ["users", params],
    queryFn: () =>
      apiFetch("/api/dashboard/users", params as Record<string, string | number>),
  });
}

export function useAnalytics() {
  return useQuery<AnalyticsData>({
    queryKey: ["analytics"],
    queryFn: () => apiFetch("/api/dashboard/analytics"),
    refetchInterval: 30_000,
  });
}

export function useTranscript(callSid: string | null, isLive = false) {
  return useQuery<TranscriptResponse>({
    queryKey: ["transcript", callSid],
    queryFn: () => apiFetch(`/api/dashboard/calls/${callSid}/transcript`),
    enabled: !!callSid,
    refetchInterval: isLive ? 2_000 : false,
  });
}

export function useTranslate() {
  return useMutation<
    TranslateResponse,
    Error,
    { texts: string[]; source_language: string }
  >({
    mutationFn: (body) => apiPost("/api/dashboard/translate", body),
  });
}

export function useEndCall() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (callSid: string) =>
      apiFetch(`/api/dashboard/calls/${callSid}/end`, {}, "POST"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["active-calls"] });
      qc.invalidateQueries({ queryKey: ["calls"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useHealth() {
  return useQuery<HealthData>({
    queryKey: ["health"],
    queryFn: () => apiFetch("/api/health"),
    refetchInterval: 10_000,
  });
}
