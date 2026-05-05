"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getJob, ingest, listWorks } from "@/lib/api";

export default function CorpusPage() {
  const qc = useQueryClient();
  const [sourceType, setSourceType] = useState<"gutenberg" | "wikisource">("gutenberg");
  const [locator, setLocator] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const worksQuery = useQuery({
    queryKey: ["works"],
    queryFn: () => listWorks()
  });

  const ingestMut = useMutation({
    mutationFn: () => ingest({ source_type: sourceType, locator: locator.trim() }),
    onSuccess: (data) => {
      setMessage(null);
      if (data.job_id) {
        setActiveJobId(data.job_id);
      } else {
        setActiveJobId(null);
        setMessage("Work is already ingested (complete). No new job.");
      }
      void qc.invalidateQueries({ queryKey: ["works"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof ApiError ? e.messageFromApi() : String(e);
      setMessage(msg);
    }
  });

  const jobQuery = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => getJob(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (!s) return 2000;
      if (s === "succeeded" || s === "failed") return false;
      return 2000;
    }
  });

  useEffect(() => {
    if (jobQuery.data?.status === "succeeded") {
      void qc.invalidateQueries({ queryKey: ["works"] });
    }
  }, [jobQuery.data?.status, qc]);

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Corpus builder</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Add a Gutenberg ID/URL or English Wikisource URL. The worker must be running to process
          jobs.
        </p>
      </div>

      <form
        className="max-w-xl space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (!locator.trim()) return;
          ingestMut.mutate();
        }}
      >
        <div>
          <label className="block text-sm font-medium text-zinc-700">Source</label>
          <select
            className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm"
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as "gutenberg" | "wikisource")}
          >
            <option value="gutenberg">Project Gutenberg</option>
            <option value="wikisource">Wikisource</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-700">Locator</label>
          <input
            className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
            placeholder={sourceType === "gutenberg" ? "e.g. 1342 or Gutenberg URL" : "Wikisource URL"}
            value={locator}
            onChange={(e) => setLocator(e.target.value)}
          />
        </div>
        {message && (
          <p className="text-sm text-amber-800 bg-amber-50 rounded-lg px-3 py-2">{message}</p>
        )}
        {ingestMut.isError && !message && (
          <p className="text-sm text-red-700 bg-red-50 rounded-lg px-3 py-2">
            {(ingestMut.error as ApiError)?.messageFromApi?.() ?? "Ingest failed"}
          </p>
        )}
        <button
          type="submit"
          disabled={ingestMut.isPending || !locator.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {ingestMut.isPending ? "Submitting…" : "Ingest"}
        </button>
      </form>

      {activeJobId && jobQuery.data && (
        <section className="max-w-xl space-y-2 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-zinc-800">Latest job</h2>
          <p className="text-xs font-mono text-zinc-500">{activeJobId}</p>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                jobQuery.data.status === "succeeded"
                  ? "bg-emerald-100 text-emerald-800"
                  : jobQuery.data.status === "failed"
                    ? "bg-red-100 text-red-800"
                    : "bg-amber-100 text-amber-800"
              }`}
            >
              {jobQuery.data.status}
            </span>
            <span className="text-xs text-zinc-600">
              stage: {String((jobQuery.data.progress as { stage?: string }).stage ?? "—")}
            </span>
          </div>
          {jobQuery.data.error && (
            <p className="text-sm text-red-700">{jobQuery.data.error}</p>
          )}
          <button
            type="button"
            className="text-xs text-zinc-500 hover:text-zinc-700"
            onClick={() => setActiveJobId(null)}
          >
            Dismiss job panel
          </button>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold text-zinc-900">Library</h2>
        {worksQuery.isLoading && <p className="mt-2 text-sm text-zinc-500">Loading works…</p>}
        {worksQuery.isError && (
          <p className="mt-2 text-sm text-red-600">Could not load works (is the API up?).</p>
        )}
        {worksQuery.data && (
          <ul className="mt-4 divide-y divide-zinc-200 rounded-xl border border-zinc-200 bg-white">
            {worksQuery.data.works.length === 0 && (
              <li className="px-4 py-6 text-sm text-zinc-500">No works yet.</li>
            )}
            {worksQuery.data.works.map((w) => (
              <li key={w.work_id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <Link
                    href={`/works/${w.work_id}`}
                    className="font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    {w.title ?? "Untitled"}
                  </Link>
                  <p className="text-xs text-zinc-500">
                    {w.author ?? "Unknown author"} · {w.source_type} · {w.ingestion_state}
                  </p>
                </div>
                <span className="text-xs font-mono text-zinc-400">{w.work_id}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
