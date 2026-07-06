import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, fetchHealth } from "./client";
import type {
  DashboardStats,
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
