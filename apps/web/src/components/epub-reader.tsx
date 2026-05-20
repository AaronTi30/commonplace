"use client";

import { useEffect, useRef, useState } from "react";
import type { Book, NavItem, Rendition } from "epubjs";
import { API_BASE_URL, getReadingProgress, putReadingProgress } from "@/lib/api";
import {
  buildTocFromEpubBuffer,
  formatChapterLabel,
  type EpubTocItem,
} from "@/lib/epub-toc";

type EpubFactory = typeof import("epubjs").default;

function flattenToc(items: NavItem[], depth = 0): EpubTocItem[] {
  const out: EpubTocItem[] = [];
  for (const item of items) {
    if (item.label?.trim() && item.href) {
      out.push({
        id: item.id || item.href,
        label: formatChapterLabel(item.label.trim()),
        href: item.href,
        depth,
      });
    }
    if (item.subitems?.length) {
      out.push(...flattenToc(item.subitems, depth + 1));
    }
  }
  return out;
}

function isPlaceholderToc(items: EpubTocItem[]): boolean {
  if (items.length === 0) return true;
  if (items.length > 1) return false;
  return /^(start|title\s*page|cover)$/i.test(items[0].label);
}

async function loadTocFromBuffer(
  data: ArrayBuffer,
  book: Book,
): Promise<EpubTocItem[]> {
  const fromZip = await buildTocFromEpubBuffer(data);
  if (fromZip.length > 0) return fromZip;

  const nav = await book.loaded.navigation;
  const fromNav = flattenToc(nav.toc);
  if (!isPlaceholderToc(fromNav)) return fromNav;
  return [];
}

type Props = {
  workId: string;
};

export function EpubReader({ workId }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const renditionRef = useRef<Rendition | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [toc, setToc] = useState<EpubTocItem[]>([]);
  const [tocLoading, setTocLoading] = useState(true);
  const [tocOpen, setTocOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const r = renditionRef.current;
    if (!r) return;
    const mount = mountRef.current;
    if (!mount) return;

    const id = requestAnimationFrame(() => {
      const width = Math.max(mount.clientWidth, 320);
      const height = Math.max(mount.clientHeight, 400);
      try {
        r.spread("none");
        r.resize(width, height);
      } catch {
        // ignore
      }
    });
    return () => cancelAnimationFrame(id);
  }, [tocOpen]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let disposed = false;
    let book: Book | null = null;
    let rendition: Rendition | null = null;

    function measureMount() {
      const el = mountRef.current;
      if (!el) return { width: 0, height: 0 };
      return {
        width: Math.max(el.clientWidth, 320),
        height: Math.max(el.clientHeight, 400),
      };
    }

    async function fitRendition() {
      const r = renditionRef.current;
      if (!r || disposed) return;
      const { width, height } = measureMount();
      if (width < 1 || height < 1) return;
      try {
        r.spread("none");
        r.resize(width, height);
      } catch {
        // manager not ready yet
      }
    }

    async function init() {
      try {
        const { default: ePub } = (await import("epubjs")) as { default: EpubFactory };

        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        if (disposed || !mountRef.current) return;

        const res = await fetch(`${API_BASE_URL}/api/works/${workId}/file`);
        if (!res.ok) throw new Error(`file fetch ${res.status}`);
        const data = await res.arrayBuffer();
        if (disposed) return;

        book = ePub(data);
        const tocPromise = loadTocFromBuffer(data, book);

        await book.ready;
        if (disposed || !mountRef.current) return;

        const { width, height } = measureMount();

        rendition = book.renderTo(mountRef.current, {
          width,
          height,
          flow: "paginated",
          spread: "none",
          minSpreadWidth: 9999,
        });
        renditionRef.current = rendition;

        rendition.on("relocated", (location: { start: { cfi: string } }) => {
          if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
          saveTimerRef.current = setTimeout(() => {
            void putReadingProgress(workId, location.start.cfi);
          }, 1000);
        });

        void tocPromise
          .then((items) => {
            if (!disposed) {
              setToc(items);
              setTocLoading(false);
            }
          })
          .catch(() => {
            if (!disposed) setTocLoading(false);
          });

        let position: string | null = null;
        try {
          const progress = await getReadingProgress(workId);
          position = progress.position;
        } catch {
          // no saved progress
        }

        if (disposed || !rendition) return;

        try {
          if (position) {
            await rendition.display(position);
          } else {
            await rendition.display();
          }
        } catch {
          await rendition.display();
        }

        rendition.spread("none");
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        await fitRendition();

        if (!disposed) setLoading(false);
      } catch {
        if (!disposed) {
          setLoadError("Could not open this file. Try re-uploading it.");
          setLoading(false);
        }
      }
    }

    void init();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "ArrowRight") {
        e.preventDefault();
        void renditionRef.current?.next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        void renditionRef.current?.prev();
      }
    }

    function onWindowResize() {
      void fitRendition();
    }

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onWindowResize);

    return () => {
      disposed = true;
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", onWindowResize);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      renditionRef.current = null;
      try {
        rendition?.destroy();
        book?.destroy();
      } catch {
        // ignore strict-mode teardown races
      }
    };
  }, [workId]);

  function turnPage(direction: "prev" | "next") {
    const r = renditionRef.current;
    if (!r) return;
    void (direction === "next" ? r.next() : r.prev());
  }

  if (loadError) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-red-600">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      {tocOpen && (
        <div className="absolute left-0 top-0 z-20 h-full w-64 overflow-y-auto border-r border-zinc-200 bg-white p-4 pb-16 shadow-lg">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Contents
          </p>
          {tocLoading && (
            <p className="text-sm text-zinc-500">Loading chapters…</p>
          )}
          {!tocLoading && toc.length === 0 && (
            <p className="text-sm text-zinc-500">
              No chapter list in this file. Use ‹ › or arrow keys to turn pages.
            </p>
          )}
          <ul className="space-y-1">
            {toc.map((item, index) => (
              <li key={`${item.href}-${index}`}>
                <button
                  type="button"
                  className="w-full truncate text-left text-sm text-zinc-700 hover:text-indigo-600"
                  style={{ paddingLeft: `${item.depth * 0.75}rem` }}
                  onClick={() => {
                    void renditionRef.current?.display(item.href);
                    setTocOpen(false);
                  }}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        className="absolute bottom-4 left-4 z-30 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 shadow-sm hover:bg-zinc-50"
        onClick={() => setTocOpen((o) => !o)}
      >
        {tocOpen ? "Close contents" : "Contents"}
      </button>

      <div
        className={`flex min-h-0 flex-1 items-stretch transition-[margin] duration-200 ${tocOpen ? "ml-64" : ""}`}
      >
        <button
          type="button"
          aria-label="Previous page"
          className="z-10 flex w-12 shrink-0 items-center justify-center text-2xl text-zinc-400 transition-colors hover:text-zinc-800"
          onClick={() => turnPage("prev")}
        >
          ‹
        </button>
        <div className="epub-viewer relative min-h-0 flex-1 overflow-hidden">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white text-sm text-zinc-500">
              Opening book…
            </div>
          )}
          <div ref={mountRef} className="h-full min-h-[400px] w-full" />
        </div>
        <button
          type="button"
          aria-label="Next page"
          className="z-10 flex w-12 shrink-0 items-center justify-center text-2xl text-zinc-400 transition-colors hover:text-zinc-800"
          onClick={() => turnPage("next")}
        >
          ›
        </button>
      </div>
    </div>
  );
}
