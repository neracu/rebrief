export type TokenStats = {
  raw_codebase_tokens: number;
  brief_tokens: number;
  savings_percentage: number;
  tokenizer: string;
};

export type ScanResponse = {
  cached: boolean;
  repo: {
    url: string;
    display_name: string;
    commit_sha: string;
  };
  markdown: string;
  token_stats: TokenStats;
  tech_stack: {
    languages: string[];
    frameworks: string[];
    manifests: string[];
  };
  risks: {
    critical: number;
    warning: number;
    info: number;
  };
  mode: "full" | "incremental";
  diff_ref: string | null;
};

export type ScanRequest = {
  url: string;
  min_confidence?: "high" | "medium" | "low";
  diff_ref?: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function postScan(body: ScanRequest): Promise<ScanResponse> {
  const response = await fetch(`${API_BASE}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const payload = (await response.json().catch(() => null)) as
    | ScanResponse
    | { detail?: unknown }
    | null;

  if (!response.ok) {
    const errorPayload =
      payload && typeof payload === "object" && "detail" in payload
        ? payload
        : null;
    throw new Error(formatDetail(errorPayload, response.status));
  }
  if (!payload || !("markdown" in payload)) {
    throw new Error("Unexpected response from scan API.");
  }
  return payload;
}

function formatDetail(payload: { detail?: unknown } | null, status: number): string {
  const detail = payload && "detail" in payload ? payload.detail : null;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return null;
      })
      .filter(Boolean);
    if (parts.length) {
      return parts.join("; ");
    }
  }
  if (status === 429) {
    return "Rate limit exceeded: 10 scans per minute per IP.";
  }
  if (status === 504) {
    return "Scan timed out.";
  }
  return `Scan failed (${status}).`;
}
