const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  // Session missing or expired: send the user to the login screen. Auth
  // endpoints are exempt so the login page can handle its own errors.
  if (
    resp.status === 401 &&
    !path.startsWith("/auth/") &&
    window.location.pathname !== "/login"
  ) {
    window.location.assign("/login");
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    // Machine not activated: everything (including login) is locked until an
    // activation code is entered.
    if (
      resp.status === 403 &&
      detail === "Activation required" &&
      window.location.pathname !== "/activate"
    ) {
      window.location.assign("/activate");
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return resp.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  delete: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
};

export const reportUrl = (searchId: string, format: "json" | "html" | "pdf") =>
  `${BASE}/searches/${searchId}/report?format=${format}`;

// /health lives outside the /api/v1 prefix.
export async function fetchHealth<T>(): Promise<T> {
  const resp = await fetch("/health");
  if (!resp.ok) throw new ApiError(resp.status, resp.statusText);
  return resp.json() as Promise<T>;
}
