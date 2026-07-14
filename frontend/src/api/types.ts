// API types mirroring backend/app/schemas/search.py

export type SearchStatus = "pending" | "running" | "completed" | "failed";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface SearchCreate {
  full_name: string;
  date_of_birth?: string | null;
  country?: string | null;
  /** Optional — enables the DVLA driving licence check. */
  driving_licence_number?: string | null;
  /** Required attestation whenever a licence number is supplied. */
  licence_check_consent?: boolean;
}

export interface SearchOut {
  id: string;
  full_name: string;
  date_of_birth: string | null;
  country: string | null;
  status: SearchStatus;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  results_count: number;
  risk_score_value: number | null;
  risk_level: RiskLevel | null;
  sources_searched: string[] | null;
}

export interface SearchResultOut {
  id: string;
  source_name: string;
  category: string;
  title: string;
  description: string | null;
  url: string | null;
  event_date: string | null;
  subject_name: string | null;
  location: string | null;
  confidence: number;
  risk_contribution: number;
}

export interface SearchDetail extends SearchOut {
  results: SearchResultOut[];
  report_reference: string | null;
}

export interface PaginatedSearches {
  items: SearchOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface SourceOut {
  name: string;
  display_name: string;
  description: string | null;
  enabled: boolean;
  /** False when the connector lacks credentials and will be skipped in live mode. */
  configured: boolean;
}

export interface HealthInfo {
  status: string;
  version: string;
  mock_connectors: boolean;
  /** Configurable display name (APP_NAME in .env). */
  app_name: string;
}

export interface AuthStatus {
  /** False until the first-launch setup has chosen a username/password. */
  configured: boolean;
  authenticated: boolean;
}

export interface DashboardStats {
  total_searches: number;
  running_searches: number;
  completed_searches: number;
  failed_searches: number;
  high_risk_searches: number;
  recent_searches: SearchOut[];
  high_risk_recent: SearchOut[];
}
