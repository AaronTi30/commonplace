"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getWork } from "@/lib/api";

type Props = {
  workId: string;
};

export function WorkDetailView({ workId }: Props) {
  const q = useInfiniteQuery({
    queryKey: ["work", workId],
    queryFn: ({ pageParam }) =>
      getWork(workId, {
        cursor: pageParam as string | undefined,
        limit: 50
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined
  });

  const pages = q.data?.pages ?? [];
  const work = pages[0]?.work as Record<string, unknown> | undefined;
  const passages = pages.flatMap((p) => p.passages);

  return (
    <div className="space-y-8">
      <p className="text-sm">
        <Link href="/corpus" className="text-indigo-600 hover:underline">
          ← Library
        </Link>
      </p>

      {q.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {q.isError && (
        <p className="text-sm text-red-600">
          Work not found or API unavailable.
        </p>
      )}

      {work && (
        <header className="border-b border-zinc-200 pb-6">
          <h1 className="text-2xl font-semibold text-zinc-900">
            {(work.title as string) ?? "Untitled"}
          </h1>
          <p className="mt-2 text-sm text-zinc-600">
            {(work.author as string) ?? "Unknown author"}
            {work.language ? ` · ${work.language as string}` : ""}
          </p>
          <p className="mt-1 text-xs text-zinc-400 font-mono">{workId}</p>
        </header>
      )}

      <section>
        <h2 className="text-lg font-semibold text-zinc-900">Passages</h2>
        <ul className="mt-4 space-y-6">
          {passages.map((p) => (
            <li key={p.passage_id} className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-500">¶{p.passage_index}</span>
                <button
                  type="button"
                  className="rounded border border-zinc-200 px-2 py-0.5 text-xs text-zinc-600 hover:bg-zinc-50"
                  onClick={() => void navigator.clipboard.writeText(p.citation_string)}
                >
                  Copy citation
                </button>
              </div>
              {p.section_label && (
                <p className="mt-1 text-xs font-medium text-indigo-700">{p.section_label}</p>
              )}
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-zinc-800">
                {p.cleaned_text}
              </p>
              <p className="mt-3 text-xs text-zinc-500">{p.citation_string}</p>
            </li>
          ))}
        </ul>
        {q.hasNextPage && (
          <button
            type="button"
            className="mt-6 rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm text-zinc-800 hover:bg-zinc-50 disabled:opacity-50"
            onClick={() => void q.fetchNextPage()}
            disabled={q.isFetchingNextPage}
          >
            {q.isFetchingNextPage ? "Loading…" : "Load more passages"}
          </button>
        )}
        {!q.hasNextPage && passages.length > 0 && (
          <p className="mt-4 text-xs text-zinc-400">End of work.</p>
        )}
      </section>
    </div>
  );
}
