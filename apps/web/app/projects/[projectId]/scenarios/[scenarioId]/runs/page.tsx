import { ScenarioRunListPageClient } from "./ScenarioRunListPageClient";

type PageParams = Promise<{
  projectId: string;
  scenarioId: string;
}>;

export default async function ScenarioRunListPage({ params }: { params: PageParams }) {
  const { projectId, scenarioId } = await params;

  return <ScenarioRunListPageClient projectId={projectId} scenarioId={scenarioId} />;
}
