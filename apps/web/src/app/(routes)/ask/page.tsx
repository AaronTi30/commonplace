"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, ask } from "@/lib/api";
import { MarkdownBody } from "@/components/markdown-body";

export default function AskPage() {
  const [q, setQ] = useState("");
  const [k, setK] = useState(5);
  const [mode, setMode] = useState<"strict" | "fluent">("strict");
  const [sourceFilter, setSourceFilter] = useState<"" | "gutenberg" | "wikisource">("");
  const [author, setAuthor] = useState("");

  const filters =
    sourceFilter || author.trim()
      ? {
          ...(sourceFilter ? { source_type: [sourceFilter] as ("gutenberg" | "wikisource")[] } : {}),
          ...(author.trim() ? { author: [author.trim()] } : {})
        }
      : undefined;

  const mut = useMutation({
    mutationFn: () =>
      ask({
        query: q.trim(),
        k,
        mode,
        ...(filters ? { filters } : {})
      })
  });

  const data = mut.data;
  const cited = new Set(data?.cited_passage_ids ?? []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Ask</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Grounded answers from retrieved passages. Strict mode validates quotes; fluent mode uses{" "}
          <code className="rounded bg-zinc-100 px-1">[1]</code> markers.
        </p>
      </div>

      <div className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div>
          <label className="block text-sm font-medium text-zinc-700">Question</label>
          <textarea
            className="mt-1 w-full min-h-[88px] rounded-lg border border-zinc-300 px-3 py-2 text-sm"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Your question…"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700">k (passages)</label>
            <input
              type="number"
              min={1}
              max={20}
              className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
              value={k}
              onChange={(e) => setK(Number(e.target.value) || 5)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700">Mode</label>
            <select
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as "strict" | "fluent")}
            >
              <option value="strict">Strict (grounded JSON)</option>
              <option value="fluent">Fluent (prose + [N])</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700">Source</label>
            <select
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={sourceFilter}
              onChange={(e) =>
                setSourceFilter(e.target.value as "" | "gutenberg" | "wikisource")
              }
            >
              <option value="">Any</option>
              <option value="gutenberg">Gutenberg</option>
              <option value="wikisource">Wikisource</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700">Author contains</label>
            <input
              className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </div>
        </div>
        <button
          type="button"
          disabled={mut.isPending || !q.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? "Asking…" : "Ask"}
        </button>
        {mut.isError && (
          <p className="text-sm text-red-700">
            {(mut.error as ApiError)?.messageFromApi?.() ?? "Request failed"}
          </p>
        )}
      </div>

      {data && (
        <div className="grid gap-8 lg:grid-cols-2">
          <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Answer</h2>
            <MarkdownBody content={data.answer_markdown} className="mt-3" />
            <dl className="mt-6 space-y-1 text-xs text-zinc-500">
              <div>
                <dt className="inline font-medium">Embedding:</dt>{" "}
                <dd className="inline">{String(data.meta.embedding_model)}</dd>
              </div>
              <div>
                <dt className="inline font-medium">LLM:</dt>{" "}
                <dd className="inline">{String(data.meta.llm_model)}</dd>
              </div>
              <div>
                <dt className="inline font-medium">k:</dt>{" "}
                <dd className="inline">{String(data.meta.k)}</dd>
              </div>
              {"timestamp" in data.meta && (
                <div>
                  <dt className="inline font-medium">Time:</dt>{" "}
                  <dd className="inline">{String(data.meta.timestamp)}</dd>
                </div>
              )}
              {"strict_validation" in data.meta && data.meta.strict_validation != null && (
                <div>
                  <dt className="inline font-medium">Validation:</dt>{" "}
                  <dd className="inline font-mono text-[11px]">
                    {JSON.stringify(data.meta.strict_validation)}
                  </dd>
                </div>
              )}
            </dl>
          </section>

          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
              Evidence ({data.retrieved_passages.length} passages)
            </h2>
            <ul className="mt-3 space-y-3">
              {data.retrieved_passages.map((p, i) => (
                <li
                  key={p.passage_id}
                  className={`rounded-lg border p-3 text-sm ${
                    cited.has(p.passage_id)
                      ? "border-indigo-300 bg-indigo-50/60"
                      : "border-zinc-200 bg-white"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-zinc-500">
                      [{i + 1}] · score {p.score.toFixed(4)}
                    </span>
                    {cited.has(p.passage_id) && (
                      <span className="text-[10px] font-semibold uppercase text-indigo-600">
                        Cited
                      </span>
                    )}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-zinc-800">{p.cleaned_text}</p>
                  <p className="mt-2 text-xs text-zinc-500">{p.citation_string}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
