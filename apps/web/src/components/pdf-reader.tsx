"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE_URL, getReadingProgress, putReadingProgress } from "@/lib/api";

type Props = {
  workId: string;
};

export function PdfReader({ workId }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const mount = mountRef.current;

    async function load() {
      try {
        const pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();

        const url = `${API_BASE_URL}/api/works/${workId}/file`;
        const pdf = await pdfjsLib.getDocument(url).promise;
        if (cancelled) return;

        const { position } = await getReadingProgress(workId);
        const targetPage = position ? parseInt(position, 10) : 1;

        setLoading(false);

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          if (cancelled || !mountRef.current) break;
          const page = await pdf.getPage(pageNum);
          const viewport = page.getViewport({ scale: 1.5 });

          const canvas = document.createElement("canvas");
          canvas.height = viewport.height;
          canvas.width = viewport.width;
          canvas.dataset.page = String(pageNum);
          canvas.className = "mx-auto mb-4 shadow-sm";

          mountRef.current.appendChild(canvas);

          const ctx = canvas.getContext("2d")!;
          await page.render({ canvas, canvasContext: ctx, viewport }).promise;
        }

        if (!cancelled && mountRef.current && targetPage > 1) {
          const target = mountRef.current.querySelector(
            `[data-page="${targetPage}"]`,
          );
          target?.scrollIntoView({ block: "start" });
        }

        if (mountRef.current) {
          const observer = new IntersectionObserver(
            (entries) => {
              const visible = entries
                .filter((e) => e.isIntersecting)
                .map((e) => parseInt((e.target as HTMLElement).dataset.page ?? "1", 10))
                .sort((a, b) => a - b);
              if (visible.length === 0) return;
              const currentPage = visible[0];
              if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
              saveTimerRef.current = setTimeout(() => {
                void putReadingProgress(workId, String(currentPage));
              }, 1000);
            },
            { threshold: 0.5 },
          );
          mountRef.current
            .querySelectorAll("canvas[data-page]")
            .forEach((el) => observer.observe(el));
        }
      } catch {
        if (!cancelled) setLoadError("Could not open this file. Try re-uploading it.");
      }
    }

    void load();

    return () => {
      cancelled = true;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (mount) {
        while (mount.firstChild) {
          mount.removeChild(mount.firstChild);
        }
      }
    };
  }, [workId]);

  if (loadError) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-red-600">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-zinc-100 p-6">
      {loading && (
        <p className="text-center text-sm text-zinc-500">Loading PDF…</p>
      )}
      <div ref={mountRef} />
    </div>
  );
}
