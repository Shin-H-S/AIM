import { ResultPageClient } from "./ResultPageClient";

type PageParams = Promise<{
  projectId: string;
  checkRunId: string;
}>;

export default async function CheckRunResultPage({ params }: { params: PageParams }) {
  const { projectId, checkRunId } = await params;

  return <ResultPageClient projectId={projectId} checkRunId={checkRunId} />;
}
