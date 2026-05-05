import { WorkDetailView } from "./work-detail";

type PageProps = {
  params: Promise<{ workId: string }>;
};

export default async function WorkDetailPage(props: PageProps) {
  const { workId } = await props.params;
  return <WorkDetailView workId={workId} />;
}
