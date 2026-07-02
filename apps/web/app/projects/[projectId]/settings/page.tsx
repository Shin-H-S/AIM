import { ProjectFormPageClient } from "../../ProjectFormPageClient";

type ProjectSettingsPageProps = {
  params: Promise<{
    projectId: string;
  }>;
};

export default async function ProjectSettingsPage({ params }: ProjectSettingsPageProps) {
  const { projectId } = await params;

  return <ProjectFormPageClient mode="edit" projectId={projectId} />;
}
