type PageProps = {
  params: Promise<{ workId: string }>;
};

export default async function WorkDetailPage(props: PageProps) {
  const { workId } = await props.params;

  return (
    <main style={{ padding: 24, fontFamily: "ui-sans-serif, system-ui" }}>
      <h1 style={{ fontSize: 24, fontWeight: 600 }}>Work Detail</h1>
      <p style={{ marginTop: 12, color: "#444" }}>
        Placeholder page for work <code>{workId}</code>. UI will be implemented in
        later tasks.
      </p>
    </main>
  );
}

