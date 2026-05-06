import Link from "next/link";

const links = [
  { href: "/", label: "Home" },
  { href: "/corpus", label: "Corpus" },
  { href: "/search", label: "Search" },
  { href: "/ask", label: "Ask" }
] as const;

export function Nav() {
  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <Link href="/" className="font-semibold text-zinc-900">
          commonplace
        </Link>
        <nav className="flex flex-wrap gap-4 text-sm">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-zinc-600 hover:text-indigo-600"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
