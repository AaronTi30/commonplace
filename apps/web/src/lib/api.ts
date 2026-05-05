const baseUrl = () =>
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, payload: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.payload = payload;
  }

  messageFromApi(): string {
    const p = this.payload as { error?: { message?: string } } | null;
    return p?.error?.message ?? this.message;
  }
}

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { json?: unknown }
): Promise<T> {
  const { json, headers: hdr, ...rest } = init ?? {};
  const headers = new Headers(hdr);
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${baseUrl()}${path}`, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body
  });
  const data = await parseJson(res);
  if (!res.ok) {
    throw new ApiError(res.status, data);
  }
  return data as T;
}

/** ----- typed endpoints ----- */

export type WorkSummary = {
  work_id: string;
  title: string | null;
  author: string | null;
  language: string | null;
  source_type: string;
  ingestion_state: string;
  ingested_at: string | null;
  created_at: string;
};

export async function listWorks(params?: {
  source_type?: string;
  author?: string;
  title?: string;
}): Promise<{ works: WorkSummary[] }> {
  const q = new URLSearchParams();
  if (params?.source_type) q.set("source_type", params.source_type);
  if (params?.author) q.set("author", params.author);
  if (params?.title) q.set("title", params.title);
  const qs = q.toString();
  return apiFetch(`/api/works${qs ? `?${qs}` : ""}`);
}

export async function ingest(body: {
  source_type: "gutenberg" | "wikisource";
  locator: string;
}): Promise<{ work_id: string; job_id: string | null }> {
  return apiFetch("/api/ingest", { method: "POST", json: body });
}

export type JobResponse = {
  job_id: string;
  status: string;
  progress: Record<string, unknown>;
  error: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
};

export async function getJob(jobId: string): Promise<JobResponse> {
  return apiFetch(`/api/jobs/${jobId}`);
}

export type PassageRow = {
  passage_id: string;
  passage_index: number;
  section_label: string | null;
  cleaned_text: string;
  citation_string: string;
};

export async function getWork(
  workId: string,
  opts?: { cursor?: string; limit?: number }
): Promise<{
  work: Record<string, unknown>;
  passages: PassageRow[];
  next_cursor?: string;
}> {
  const q = new URLSearchParams();
  if (opts?.cursor) q.set("cursor", opts.cursor);
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  const qs = q.toString();
  return apiFetch(`/api/works/${workId}${qs ? `?${qs}` : ""}`);
}

export type SearchHit = {
  passage_id: string;
  work_id: string;
  citation_string: string;
  cleaned_text_snippet: string;
  score: number;
};

export async function search(body: {
  query: string;
  k?: number;
  filters?: {
    source_type?: string[];
    author?: string[];
    work_ids?: string[];
    language?: string[];
  };
}): Promise<{ results: SearchHit[]; meta: { k: number; embedding_model: string } }> {
  return apiFetch("/api/search", { method: "POST", json: body });
}

export type RetrievedPassage = {
  passage_id: string;
  work_id: string;
  citation_string: string;
  cleaned_text: string;
  score: number;
};

export async function ask(body: {
  query: string;
  k?: number;
  mode?: "strict" | "fluent";
  filters?: {
    source_type?: string[];
    author?: string[];
    work_ids?: string[];
    language?: string[];
  };
}): Promise<{
  answer_markdown: string;
  retrieved_passages: RetrievedPassage[];
  cited_passage_ids: string[];
  meta: Record<string, unknown>;
}> {
  return apiFetch("/api/ask", { method: "POST", json: body });
}
