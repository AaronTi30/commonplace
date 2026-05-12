"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { search } from "@/lib/api";

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [k, setK] = useState(10);
  const [sourceFilter, setSourceFilter] = useState<"" | "gutenberg" | "wikisource">("");
  const [author, setAuthor] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 400);
    return () => clearTimeout(t);
  }, [q]);

  const filters =
    sourceFilter || author.trim()
      ? {
          ...(sourceFilter ? { source_type: [sourceFilter] as ("gutenberg" | "wikisource")[] } : {}),
          ...(author.trim() ? { author: [author.trim()] } : {})
        }
      : undefined;

  const searchQuery = useQuery({
    queryKey: ["search", debounced, k, filters],
    queryFn: () =>
      search({
        query: debounced.trim(),
        k,
        ...(filters ? { filters } : {})
      }),
    enabled: debounced.trim().length > 0
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Search</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Semantic passage search over your ingested corpus (pgvector + MiniLM).
        </p>
      </div>

      <div className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div>
          <label className="block text-sm font-medium text-zinc-700">Query</label>
          <input
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. virtue and the good life"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="block text-sm font-medium text-zinc-700">k</label>
            <input
              type="number"
              min={1}
              max={50}
              className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
              value={k}
              onChange={(e) => setK(Number(e.target.value) || 10)}
            />
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
              placeholder="optional"
            />
          </div>
        </div>
      </div>

      {!debounced.trim() && (
        <p className="text-sm text-zinc-500">Type a query to search (debounced ~400ms).</p>
      )}

      {searchQuery.isFetching && debounced.trim() && (
        <p className="text-sm text-zinc-500">Searching…</p>
      )}
      {searchQuery.isError && (
        <p className="text-sm text-red-600">Search failed — check that the API is running.</p>
      )}
      {searchQuery.data && (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500">
            {searchQuery.data.results.length} results · model {searchQuery.data.meta.embedding_model}{" "}
            · k {searchQuery.data.meta.k}
          </p>
          <ul className="space-y-3">
            {searchQuery.data.results.map((r) => (
              <li
                key={r.passage_id}
                className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-medium text-indigo-600">
                      score {r.rrf_score.toFixed(4)}
                    </p>
                    <p className="mt-1 text-sm text-zinc-800">{r.cleaned_text_snippet}</p>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
                    onClick={() => void navigator.clipboard.writeText(r.citation_string)}
                  >
                    Copy citation
                  </button>
                </div>
                <p className="mt-2 text-xs text-zinc-500">{r.citation_string}</p>
                <Link
                  href={`/works/${r.work_id}`}
                  className="mt-2 inline-block text-xs text-indigo-600 hover:underline"
                >
                  Open work
                </Link>
              </li>
            ))}
          </ul>
          {searchQuery.data.results.length === 0 && (
            <p className="text-sm text-zinc-500">No passages matched.</p>
          )}
        </div>
      )}
    </div>
  );
}
