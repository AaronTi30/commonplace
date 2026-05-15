// Next replaces NEXT_PUBLIC_* at build time for both server + client bundles.
// Avoid runtime `typeof process` checks that can behave differently in dev.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  const res = await fetch(`${API_BASE_URL}${path}`, {
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

export async function deleteWork(workId: string): Promise<{ deleted: boolean; work_id: string }> {
  return apiFetch(`/api/works/${workId}`, { method: "DELETE" });
}

export type SearchHit = {
  passage_id: string;
  work_id: string;
  citation_string: string;
  cleaned_text_snippet: string;
  rrf_score: number;
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
}): Promise<{ results: SearchHit[]; meta: { k: number; embedding_model: string; retrieval: string } }> {
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

export type StreamAskCallbacks = {
  onPassages: (passages: RetrievedPassage[], meta: Record<string, unknown>) => void;
  onToken: (text: string) => void;
  onDone: (citedIds: string[], meta: Record<string, unknown>) => void;
  onError: (message: string) => void;
};

export async function streamAsk(
  body: {
    query: string;
    k?: number;
    filters?: {
      source_type?: string[];
      author?: string[];
      work_ids?: string[];
      language?: string[];
    };
  },
  callbacks: StreamAskCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, mode: "fluent" }),
    signal
  });

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const msg =
      (data as { error?: { message?: string } } | null)?.error?.message ?? `HTTP ${res.status}`;
    callbacks.onError(msg);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6)) as {
          type: string;
          text?: string;
          retrieved_passages?: RetrievedPassage[];
          cited_passage_ids?: string[];
          meta?: Record<string, unknown>;
          message?: string;
        };
        if (event.type === "passages") {
          callbacks.onPassages(event.retrieved_passages ?? [], event.meta ?? {});
        } else if (event.type === "token") {
          callbacks.onToken(event.text ?? "");
        } else if (event.type === "done") {
          callbacks.onDone(event.cited_passage_ids ?? [], event.meta ?? {});
        } else if (event.type === "error") {
          callbacks.onError(event.message ?? "Unknown error");
        }
      } catch {
        // malformed SSE line — skip
      }
    }
  }
}
