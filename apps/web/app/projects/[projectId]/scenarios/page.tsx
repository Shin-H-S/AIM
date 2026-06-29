import { ScenarioListPageClient } from "./ScenarioListPageClient";

type PageParams = Promise<{
  projectId: string;
}>;

export default async function ScenarioListPage({ params }: { params: PageParams }) {
  const { projectId } = await params;

  return <ScenarioListPageClient projectId={projectId} />;
}
