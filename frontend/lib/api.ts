export type QueryKind = "unbranded" | "use_case" | "comparison" | "branded";

export interface QueryItem {
  id?: number;
  text: string;
  kind: QueryKind;
  active: boolean;
}

export interface RunBrief {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  stage: string;
  trigger: "manual" | "scheduled";
  engines: string[];
  samples_per_query: number;
  progress_done: number;
  progress_total: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  visibility: number | null;
  ci: [number, number] | null;
  per_engine: Record<string, number | null>;
}

export interface Business {
  id: number;
  url: string;
  domain: string;
  name: string;
  aliases: string[];
  category: string;
  location: string;
  description: string;
  recheck_enabled: boolean;
  recheck_days: number;
  next_run_at: string | null;
  created_at: string;
  latest_run: RunBrief | null;
  latest_done_run: RunBrief | null;
  queries?: QueryItem[];
}

export interface Metrics {
  visibility: number | null;
  ci: [number, number] | null;
  mention_rate?: number;
  top3_rate?: number;
  linked_rate?: number;
  avg_position?: number | null;
  share_of_voice?: number | null;
  n: number;
}

export interface Summary {
  overall: Metrics;
  per_engine: Record<string, Metrics>;
  branded: Metrics | null;
  matrix: { query_id: number; text: string; kind: QueryKind; rates: Record<string, number | null> }[];
  engines: string[];
  n_queries_scored: number;
  n_errors: number;
  mock: boolean;
}

export interface Competitor {
  name: string;
  domain: string | null;
  appearance_rate: number;
  appearances: number;
  avg_position: number;
  top3: number;
  engines: Record<string, number>;
  n_queries: number;
}

export interface SourceGap {
  domain: string;
  type: string;
  type_label: string;
  citations: number;
  citation_rate: number;
  engines: Record<string, number>;
  n_queries: number;
  target_in_answers_rate: number;
  top_competitors: string[];
  pages: { url: string; title: string | null; citations: number; listed: boolean | null }[];
  listed: boolean | null;
}

export interface Audit {
  url: string;
  domain: string;
  name?: string | null;
  ok: boolean;
  mock?: boolean;
  error: string | null;
  checks: Record<string, unknown>;
}

export interface Evidence {
  label: string;
  url: string | null;
  kind: "observed" | "reference";
}

export interface Recommendation {
  id: number;
  rank: number;
  priority: number;
  category: "source_gap" | "site" | "content";
  title: string;
  detail: string;
  technique_id: string | null;
  evidence: Evidence[];
  done: boolean;
}

export interface RunDetail extends RunBrief {
  business_id: number;
  summary: Summary | null;
  competitors: Competitor[];
  source_gaps: SourceGap[];
  site_audit: Audit | null;
  competitor_audits: Audit[];
  recommendations: Recommendation[];
}

export interface EngineResponse {
  id: number;
  query_id: number;
  query_text: string;
  query_kind: QueryKind;
  engine: string;
  sample: number;
  text: string;
  error: string | null;
  latency_ms: number | null;
  target_mentioned: boolean;
  target_position: number | null;
  target_linked: boolean;
  mentions: { name: string; domain: string | null; position: number; is_target: boolean }[];
  citations: { url: string; domain: string; title: string | null }[];
}

export interface ProfileDraft {
  url: string;
  domain: string;
  name: string;
  category: string;
  location: string;
  description: string;
  aliases: string[];
  scrape_ok: boolean;
  needs_input: string[];
  queries: { kind: QueryKind; text: string }[];
}

export interface Health {
  ok: boolean;
  mock: boolean;
  engines: { id: string; label: string }[];
  samples_per_query: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  health: () => req<Health>("/health"),
  infer: (url: string) => req<ProfileDraft>("/profile/infer", { method: "POST", body: JSON.stringify({ url }) }),
  suggestQueries: (b: { name: string; category: string; location: string; description?: string }) =>
    req<{ queries: { kind: QueryKind; text: string }[] }>("/profile/queries", { method: "POST", body: JSON.stringify(b) }),
  businesses: () => req<Business[]>("/businesses"),
  business: (id: number) => req<Business>(`/businesses/${id}`),
  createBusiness: (b: Record<string, unknown>) =>
    req<Business & { run_id: number | null }>("/businesses", { method: "POST", body: JSON.stringify(b) }),
  patchBusiness: (id: number, b: Partial<Business>) =>
    req<Business>(`/businesses/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  deleteBusiness: (id: number) => req<void>(`/businesses/${id}`, { method: "DELETE" }),
  replaceQueries: (id: number, qs: QueryItem[]) =>
    req<QueryItem[]>(`/businesses/${id}/queries`, { method: "PUT", body: JSON.stringify(qs) }),
  startRun: (id: number, body: { engines?: string[]; samples_per_query?: number } = {}) =>
    req<RunBrief>(`/businesses/${id}/runs`, { method: "POST", body: JSON.stringify(body) }),
  runs: (id: number) => req<RunBrief[]>(`/businesses/${id}/runs`),
  run: (id: number) => req<RunDetail>(`/runs/${id}`),
  responses: (runId: number, params: { query_id?: number; engine?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.query_id != null) q.set("query_id", String(params.query_id));
    if (params.engine) q.set("engine", params.engine);
    return req<EngineResponse[]>(`/runs/${runId}/responses?${q}`);
  },
  setRecDone: (id: number, done: boolean) =>
    req<{ id: number; done: boolean }>(`/recommendations/${id}`, { method: "PATCH", body: JSON.stringify({ done }) }),
};

export const ENGINE_LABEL: Record<string, string> = { chatgpt: "ChatGPT", gemini: "Gemini", perplexity: "Perplexity" };
export const ENGINE_ORDER = ["chatgpt", "gemini", "perplexity"];
export const engineColor = (e: string) => `var(--engine-${e}, var(--muted))`;

export const KIND_LABEL: Record<QueryKind, string> = {
  unbranded: "Unbranded",
  use_case: "Use case",
  comparison: "Comparison",
  branded: "Branded",
};

export const pct = (x: number | null | undefined, digits = 0) =>
  x == null ? "–" : `${(x * 100).toFixed(digits)}%`;

export function fmtDate(iso: string | null | undefined, withTime = false) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : { year: "numeric" }),
  });
}
