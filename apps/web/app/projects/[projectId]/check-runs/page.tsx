import { CheckRunListPageClient } from "./CheckRunListPageClient";

type PageParams = Promise<{
  projectId: string;
}>;

export default async function CheckRunListPage({ params }: { params: PageParams }) {
  const { projectId } = await params;

  return <CheckRunListPageClient projectId={projectId} />;
}
