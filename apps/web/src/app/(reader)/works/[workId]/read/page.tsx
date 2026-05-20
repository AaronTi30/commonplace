import { Suspense } from "react";
import { ReadingView } from "./reading-view";

type Props = {
  params: Promise<{ workId: string }>;
};

export default async function ReadPage({ params }: Props) {
  const { workId } = await params;
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-zinc-500">Loading…</div>}>
      <ReadingView workId={workId} />
    </Suspense>
  );
}
