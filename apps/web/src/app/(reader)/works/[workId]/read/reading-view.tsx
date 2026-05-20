"use client";

import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getWork } from "@/lib/api";

const EpubReader = dynamic(
  () => import("@/components/epub-reader").then((m) => m.EpubReader),
  { ssr: false, loading: () => <ReaderLoading /> },
);

const PdfReader = dynamic(
  () => import("@/components/pdf-reader").then((m) => m.PdfReader),
  { ssr: false, loading: () => <ReaderLoading /> },
);

function ReaderLoading() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-zinc-500">
      Loading reader…
    </div>
  );
}

type Props = {
  workId: string;
};

export function ReadingView({ workId }: Props) {
  const router = useRouter();
  const workQuery = useQuery({
    queryKey: ["work-read", workId],
    queryFn: () => getWork(workId, { limit: 1 }),
  });

  if (workQuery.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-zinc-500">
        Loading…
      </div>
    );
  }

  if (workQuery.isError || !workQuery.data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3">
        <p className="text-sm text-red-600">Book not found or API unavailable.</p>
        <Link href="/corpus" className="text-sm text-indigo-600 hover:underline">
          ← Back to library
        </Link>
      </div>
    );
  }

  const work = workQuery.data.work as Record<string, unknown>;
  const sourceType = work.source_type as string | undefined;

  if (sourceType && !["epub", "pdf"].includes(sourceType)) {
    router.replace(`/works/${workId}`);
    return null;
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-12 flex-none items-center gap-4 border-b border-zinc-200 bg-white px-4">
        <Link
          href={`/works/${workId}`}
          className="text-sm text-zinc-500 hover:text-zinc-900"
        >
          ← {(work.title as string) ?? "Back"}
        </Link>
        <span className="flex-1 truncate text-center text-sm font-medium text-zinc-900">
          {(work.title as string) ?? "Untitled"}
        </span>
        <span className="w-24" />
      </header>

      <main className="min-h-0 flex-1 overflow-hidden">
        {sourceType === "epub" && <EpubReader workId={workId} />}
        {sourceType === "pdf" && <PdfReader workId={workId} />}
        {!sourceType && (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-zinc-500">Unable to determine file type.</p>
          </div>
        )}
      </main>
    </div>
  );
}
