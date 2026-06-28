import { ScenarioRunResultPageClient } from "./ScenarioRunResultPageClient";

type PageParams = Promise<{
  projectId: string;
  scenarioId: string;
  scenarioRunId: string;
}>;

export default async function ScenarioRunResultPage({ params }: { params: PageParams }) {
  const { projectId, scenarioId, scenarioRunId } = await params;

  return (
    <ScenarioRunResultPageClient
      projectId={projectId}
      scenarioId={scenarioId}
      scenarioRunId={scenarioRunId}
    />
  );
}
