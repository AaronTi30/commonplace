import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          commonplace
        </h1>
        <p className="mt-2 max-w-xl text-zinc-600">
          Local-first semantic search and grounded Q&A over philosophical texts (Gutenberg +
          Wikisource). Run Postgres + API + worker, build your corpus, then search or ask with
          citations.
        </p>
      </div>
      <ul className="flex flex-col gap-3 text-sm sm:flex-row sm:flex-wrap">
        <li>
          <Link
            href="/corpus"
            className="inline-flex rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
          >
            Corpus builder
          </Link>
        </li>
        <li>
          <Link
            href="/search"
            className="inline-flex rounded-lg border border-zinc-300 bg-white px-4 py-2 font-medium text-zinc-800 hover:bg-zinc-50"
          >
            Search passages
          </Link>
        </li>
        <li>
          <Link
            href="/ask"
            className="inline-flex rounded-lg border border-zinc-300 bg-white px-4 py-2 font-medium text-zinc-800 hover:bg-zinc-50"
          >
            Ask (RAG)
          </Link>
        </li>
      </ul>
      <p className="text-xs text-zinc-500">
        Set <code className="rounded bg-zinc-100 px-1 py-0.5">NEXT_PUBLIC_API_BASE_URL</code> if
        the API is not at <code className="rounded bg-zinc-100 px-1">http://127.0.0.1:8000</code>.
      </p>
    </div>
  );
}
