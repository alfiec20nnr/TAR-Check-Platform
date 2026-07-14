import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, fetchHealth } from "./client";
import type {
  AuthStatus,
  DashboardStats,
  LicenceStatus,
  HealthInfo,
  PaginatedSearches,
  SearchCreate,
  SearchDetail,
  SearchOut,
  SourceOut,
} from "./types";

const TERMINAL = new Set(["completed", "failed"]);

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardStats>("/dashboard/stats"),
    refetchInterval: 5000,
  });
}

export function useSearches(page: number, pageSize: number, status?: string, riskLevel?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set("status", status);
  if (riskLevel) params.set("risk_level", riskLevel);
  return useQuery({
    queryKey: ["searches", page, pageSize, status ?? "", riskLevel ?? ""],
    queryFn: () => api.get<PaginatedSearches>(`/searches?${params.toString()}`),
  });
}

export function useSearchDetail(searchId: string | undefined) {
  return useQuery({
    queryKey: ["search", searchId],
    queryFn: () => api.get<SearchDetail>(`/searches/${searchId}`),
    enabled: Boolean(searchId),
    // Poll every 2s while the pipeline is running; stop once terminal.
    refetchInterval: (query) =>
      query.state.data && TERMINAL.has(query.state.data.status) ? false : 2000,
  });
}

export function useSubmitSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SearchCreate) => api.post<SearchOut>("/searches", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["searches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useDeleteSearches() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      // Sequential keeps the audit trail ordered and avoids rate-limit bursts.
      for (const id of ids) {
        await api.delete(`/searches/${id}`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["searches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useClearHistory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete<{ deleted: number }>("/searches"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["searches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useLicenceStatus() {
  return useQuery({
    queryKey: ["licence-status"],
    queryFn: () => api.get<LicenceStatus>("/licence/status"),
    staleTime: 0,
    retry: false,
  });
}

export function useActivate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { code: string }) => api.post<void>("/licence/activate", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["licence-status"] });
    },
  });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: ["auth-status"],
    queryFn: () => api.get<AuthStatus>("/auth/status"),
    staleTime: 0,
    retry: false,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      api.post<void>("/auth/login", payload),
  });
}

/** First-launch credential creation; the server logs the user straight in. */
export function useSetup() {
  return useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      api.post<void>("/auth/setup", payload),
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout", {}),
    onSuccess: () => {
      window.location.assign("/login");
    },
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => fetchHealth<HealthInfo>(),
    staleTime: Infinity,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<SourceOut[]>("/sources"),
    staleTime: 60_000,
  });
}
