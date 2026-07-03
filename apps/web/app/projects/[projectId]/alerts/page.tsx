import { AlertOverviewPageClient } from "./AlertOverviewPageClient";

type PageParams = Promise<{
  projectId: string;
}>;

export default async function AlertOverviewPage({ params }: { params: PageParams }) {
  const { projectId } = await params;

  return <AlertOverviewPageClient projectId={projectId} />;
}
