"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  deleteWork,
  getJob,
  ingest,
  listWorks,
  patchWork,
  uploadIngest,
  type WorkSummary
} from "@/lib/api";

export default function CorpusPage() {
  const qc = useQueryClient();
  const [sourceType, setSourceType] = useState<"gutenberg" | "wikisource">("gutenberg");
  const [locator, setLocator] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadAuthor, setUploadAuthor] = useState("");
  const [uploadLanguage, setUploadLanguage] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [editingWorkId, setEditingWorkId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editAuthor, setEditAuthor] = useState("");
  const [editLanguage, setEditLanguage] = useState("");

  const worksQuery = useQuery({
    queryKey: ["works"],
    queryFn: () => listWorks()
  });

  const deleteMut = useMutation({
    mutationFn: (workId: string) => deleteWork(workId),
    onSuccess: async () => {
      setMessage(null);
      await qc.invalidateQueries({ queryKey: ["works"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof ApiError ? e.messageFromApi() : String(e);
      setMessage(msg);
    }
  });

  const onIngestSuccess = (data: { work_id: string; job_id: string | null }) => {
    setMessage(null);
    if (data.job_id) {
      setActiveJobId(data.job_id);
    } else {
      setActiveJobId(null);
      setMessage("Work is already ingested (complete). No new job.");
    }
    void qc.invalidateQueries({ queryKey: ["works"] });
  };

  const ingestMut = useMutation({
    mutationFn: () => ingest({ source_type: sourceType, locator: locator.trim() }),
    onSuccess: onIngestSuccess,
    onError: (e: unknown) => {
      const msg = e instanceof ApiError ? e.messageFromApi() : String(e);
      setMessage(msg);
    }
  });

  const uploadMut = useMutation({
    mutationFn: () => {
      if (!uploadFile) throw new Error("no file");
      return uploadIngest({
        file: uploadFile,
        title: uploadTitle.trim() || undefined,
        author: uploadAuthor.trim() || undefined,
        language: uploadLanguage.trim() || undefined
      });
    },
    onSuccess: (data) => {
      setUploadFile(null);
      const input = document.getElementById("corpus-upload-file") as HTMLInputElement | null;
      if (input) input.value = "";
      onIngestSuccess(data);
    },
    onError: (e: unknown) => {
      const msg = e instanceof ApiError ? e.messageFromApi() : String(e);
      setMessage(msg);
    }
  });

  const patchMut = useMutation({
    mutationFn: (args: { workId: string; body: { title: string; author: string; language: string } }) =>
      patchWork(args.workId, {
        title: args.body.title.trim() || null,
        author: args.body.author.trim() || null,
        language: args.body.language.trim() || null
      }),
    onSuccess: async (_data, variables) => {
      setEditingWorkId(null);
      setMessage(null);
      await qc.invalidateQueries({ queryKey: ["works"] });
      await qc.invalidateQueries({ queryKey: ["work", variables.workId] });
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

  const beginEdit = (w: WorkSummary) => {
    setEditingWorkId(w.work_id);
    setEditTitle(w.title ?? "");
    setEditAuthor(w.author ?? "");
    setEditLanguage(w.language ?? "");
    setMessage(null);
  };

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Corpus builder</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Add Gutenberg/Wikisource by locator, or upload an EPUB or PDF. The worker must be running
          to process jobs.
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

      <div className="max-w-xl border-t border-zinc-200 pt-8">
        <form
          className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (!uploadFile) return;
            uploadMut.mutate();
          }}
        >
          <h2 className="text-sm font-semibold text-zinc-800">Upload EPUB or PDF</h2>
          <div>
            <label className="block text-sm font-medium text-zinc-700">File</label>
            <input
              id="corpus-upload-file"
              type="file"
              accept=".epub,.pdf,application/epub+zip,application/pdf"
              className="mt-1 block w-full text-sm text-zinc-600 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-zinc-800 hover:file:bg-zinc-200"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-1">
              <label className="block text-xs font-medium text-zinc-600">Title (optional)</label>
              <input
                className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                placeholder="Auto from file"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
              />
            </div>
            <div className="sm:col-span-1">
              <label className="block text-xs font-medium text-zinc-600">Author (optional)</label>
              <input
                className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                placeholder="Auto from file"
                value={uploadAuthor}
                onChange={(e) => setUploadAuthor(e.target.value)}
              />
            </div>
            <div className="sm:col-span-1">
              <label className="block text-xs font-medium text-zinc-600">Language (optional)</label>
              <input
                className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                placeholder="e.g. en"
                value={uploadLanguage}
                onChange={(e) => setUploadLanguage(e.target.value)}
              />
            </div>
          </div>
          {uploadMut.isError && (
            <p className="text-sm text-red-700 bg-red-50 rounded-lg px-3 py-2">
              {(uploadMut.error as ApiError)?.messageFromApi?.() ?? "Upload failed"}
            </p>
          )}
          <button
            type="submit"
            disabled={uploadMut.isPending || !uploadFile}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {uploadMut.isPending ? "Uploading…" : "Upload & ingest"}
          </button>
        </form>
      </div>

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
          {jobQuery.data.error && <p className="text-sm text-red-700">{jobQuery.data.error}</p>}
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
              <li
                key={w.work_id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:justify-between"
              >
                {editingWorkId === w.work_id ? (
                  <div className="flex w-full flex-col gap-2 sm:max-w-md">
                    <input
                      className="w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      placeholder="Title"
                    />
                    <input
                      className="w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                      value={editAuthor}
                      onChange={(e) => setEditAuthor(e.target.value)}
                      placeholder="Author"
                    />
                    <input
                      className="w-full rounded-lg border border-zinc-300 px-2 py-1.5 text-sm"
                      value={editLanguage}
                      onChange={(e) => setEditLanguage(e.target.value)}
                      placeholder="Language"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                        disabled={patchMut.isPending}
                        onClick={() =>
                          patchMut.mutate({
                            workId: w.work_id,
                            body: { title: editTitle, author: editAuthor, language: editLanguage }
                          })
                        }
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
                        onClick={() => setEditingWorkId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
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
                )}
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  <span className="text-xs font-mono text-zinc-400">{w.work_id}</span>
                  {editingWorkId !== w.work_id && (
                    <button
                      type="button"
                      className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
                      aria-label="Edit metadata"
                      onClick={() => beginEdit(w)}
                    >
                      Edit
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                    disabled={deleteMut.isPending}
                    onClick={() => {
                      const ok = window.confirm(
                        `Delete this work from your corpus?\n\n${w.title ?? "Untitled"}\n${w.work_id}`
                      );
                      if (!ok) return;
                      deleteMut.mutate(w.work_id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
