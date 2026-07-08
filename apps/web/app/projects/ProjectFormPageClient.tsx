"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createProject,
  deleteProject,
  fetchProject,
  fetchProjectVerification,
  updateProject,
  verifyProjectDomain,
  type Project,
  type ProjectEnvironment,
  type ProjectPayload,
  type ProjectVerification
} from "@/lib/api";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";
import { formatNullableDateTime } from "@/lib/format";
import { LoginRequiredNotice, Metric, Notice } from "@/components/ui";

type ProjectFormMode = "create" | "edit";

type ProjectFormState = {
  name: string;
  serviceUrl: string;
  description: string;
  environment: ProjectEnvironment;
  scanIntervalMinutes: string;
  scheduledScansEnabled: boolean;
  responseTimeThresholdMs: string;
  qualityScoreThreshold: string;
};

type LoadState = "checking-auth" | "loading" | "ready" | "unauthorized" | "not-found" | "unavailable";
type SubmitState = "idle" | "submitting" | "success" | "invalid" | "unauthorized" | "not-found" | "unavailable";
type VerificationState = "idle" | "loading" | "success" | "unauthorized" | "not-found" | "unavailable";
type VerifyActionState =
  | "idle"
  | "verifying"
  | "success"
  | "verification-failed"
  | "unauthorized"
  | "not-found"
  | "unavailable";

const initialForm: ProjectFormState = {
  name: "",
  serviceUrl: "",
  description: "",
  environment: "development",
  scanIntervalMinutes: "60",
  scheduledScansEnabled: false,
  responseTimeThresholdMs: "2000",
  qualityScoreThreshold: "80"
};

export function ProjectFormPageClient({
  mode,
  projectId
}: {
  mode: ProjectFormMode;
  projectId?: string;
}) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectFormState>(initialForm);
  const [loadState, setLoadState] = useState<LoadState>("checking-auth");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [verification, setVerification] = useState<ProjectVerification | null>(null);
  const [verificationState, setVerificationState] = useState<VerificationState>("idle");
  const [verifyActionState, setVerifyActionState] = useState<VerifyActionState>("idle");
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadVerification = useCallback(async (token: string, targetProjectId: string) => {
    setVerificationState("loading");
    const result = await fetchProjectVerification({
      projectId: targetProjectId,
      accessToken: token
    });

    if (result.state !== "success") {
      setVerification(null);
      setVerificationState(result.state);
      return;
    }

    setVerification(result.verification);
    setVerificationState("success");
  }, []);

  const loadProject = useCallback(
    async (token: string) => {
      if (!projectId) {
        setLoadState("not-found");
        return;
      }

      setLoadState("loading");
      const result = await fetchProject({
        projectId,
        accessToken: token
      });

      if (result.state !== "success") {
        if (result.state === "unauthorized") {
          clearStoredAccessToken();
        }

        setProject(null);
        setLoadState(result.state);
        return;
      }

      setProject(result.project);
      setForm(formFromProject(result.project));
      setLoadState("ready");
      await loadVerification(token, result.project.id);
    },
    [loadVerification, projectId]
  );

  useEffect(() => {
    const storedAccessToken = getStoredAccessToken();

    queueMicrotask(() => {
      if (!storedAccessToken) {
        setLoadState("unauthorized");
        return;
      }

      if (mode === "create") {
        setLoadState("ready");
        return;
      }

      void loadProject(storedAccessToken);
    });
  }, [loadProject, mode]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitMessage(null);

    const payloadResult = buildProjectPayload(form);
    if (!payloadResult.ok) {
      setSubmitState("invalid");
      setSubmitMessage(payloadResult.message);
      return;
    }

    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setSubmitState("unauthorized");
      setSubmitMessage("로그인 세션이 없습니다. 다시 로그인하세요.");
      return;
    }

    setSubmitState("submitting");
    const result =
      mode === "create"
        ? await createProject({
            accessToken,
            payload: payloadResult.payload
          })
        : await updateProject({
            projectId: projectId ?? "",
            accessToken,
            payload: payloadResult.payload
          });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessToken();
      }

      setSubmitState(result.state);
      setSubmitMessage(projectMutationMessage[result.state]);
      return;
    }

    setProject(result.project);
    setForm(formFromProject(result.project));
    setSubmitState("success");
    setSubmitMessage(
      mode === "create"
        ? "프로젝트를 생성했습니다. 도메인 인증 안내로 이동합니다."
        : "프로젝트 설정을 저장했습니다."
    );

    if (mode === "create") {
      router.replace(`/projects/${result.project.id}/settings`);
      return;
    }

    await loadVerification(accessToken, result.project.id);
  }

  async function handleVerifyProject() {
    const accessToken = getStoredAccessToken();

    if (!project || !accessToken) {
      setVerifyActionState("unauthorized");
      return;
    }

    setVerifyActionState("verifying");
    const result = await verifyProjectDomain({
      projectId: project.id,
      accessToken
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessToken();
      }

      setVerifyActionState(result.state);
      return;
    }

    setVerification(result.verification);
    setVerificationState("success");
    setVerifyActionState("success");
    setProject((currentProject) =>
      currentProject
        ? {
            ...currentProject,
            is_verified: result.verification.is_verified
          }
        : currentProject
    );
  }

  async function handleDeleteProject() {
    if (!project || isDeleting) {
      return;
    }

    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setDeleteError("로그인 세션이 없습니다. 다시 로그인하세요.");
      return;
    }

    if (deleteConfirmName.trim() !== project.name) {
      setDeleteError("확인을 위해 프로젝트 이름을 정확히 입력하세요.");
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);
    const result = await deleteProject({
      projectId: project.id,
      accessToken
    });

    if (result.state === "success") {
      router.replace("/dashboard");
      return;
    }

    if (result.state === "unauthorized") {
      clearStoredAccessToken();
      setDeleteError("로그인 세션이 만료되었습니다. 다시 로그인하세요.");
    } else if (result.state === "not-found") {
      setDeleteError("프로젝트를 찾을 수 없습니다. 이미 삭제되었을 수 있습니다.");
    } else {
      setDeleteError("삭제 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsDeleting(false);
  }

  const title = mode === "create" ? "프로젝트 생성" : "프로젝트 설정";
  const subtitle =
    mode === "create"
      ? "서비스 URL과 검사 기준을 등록합니다. 생성 후 HTML meta 태그 기반 도메인 인증 안내로 이동합니다."
      : "서비스 URL, 환경, 검사 기준을 수정하고 도메인 인증 상태를 확인합니다.";

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-700">
            AIM 프로젝트 관리
          </p>
          <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-6xl">{title}</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-600">{subtitle}</p>
        </div>

        <LoadStateNotice loadState={loadState} />

        {loadState === "ready" && (
          <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
            <ProjectForm
              form={form}
              mode={mode}
              onChange={setForm}
              onSubmit={handleSubmit}
              submitMessage={submitMessage}
              submitState={submitState}
            />

            {mode === "edit" && project ? (
              <div className="flex flex-col gap-6">
                <VerificationPanel
                  onVerify={handleVerifyProject}
                  project={project}
                  verification={verification}
                  verificationState={verificationState}
                  verifyActionState={verifyActionState}
                />
                <DangerZone
                  onDelete={() => void handleDeleteProject()}
                  deleteConfirmName={deleteConfirmName}
                  deleteError={deleteError}
                  isDeleting={isDeleting}
                  onChangeConfirmName={setDeleteConfirmName}
                  projectName={project.name}
                />
              </div>
            ) : (
              <CreationGuide />
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function DangerZone({
  deleteConfirmName,
  deleteError,
  isDeleting,
  onChangeConfirmName,
  onDelete,
  projectName
}: {
  deleteConfirmName: string;
  deleteError: string | null;
  isDeleting: boolean;
  onChangeConfirmName: (value: string) => void;
  onDelete: () => void;
  projectName: string;
}) {
  const isConfirmed = deleteConfirmName.trim() === projectName;

  return (
    <aside className="rounded-3xl border border-rose-200 bg-rose-50/60 p-6">
      <h2 className="text-2xl font-bold text-rose-800">프로젝트 삭제</h2>
      <p className="mt-2 text-sm leading-6 text-slate-500">
        프로젝트와 검사, 시나리오, 산출물 메타데이터, 알림 기록이 모두 삭제되며 되돌릴
        수 없습니다.
      </p>

      <label className="mt-5 block" htmlFor="delete_confirm_name">
        <span className="text-sm font-semibold text-slate-600">
          확인을 위해 프로젝트 이름(<span className="text-rose-700">{projectName}</span>)을
          입력하세요
        </span>
        <input
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-rose-300/0 transition placeholder:text-slate-400 focus:border-rose-500 focus:ring-4 focus:ring-rose-500/20"
          id="delete_confirm_name"
          onChange={(event) => onChangeConfirmName(event.target.value)}
          placeholder={projectName}
          value={deleteConfirmName}
        />
      </label>

      <button
        className="mt-4 w-full rounded-2xl border border-rose-300 bg-rose-50 px-5 py-3 text-sm font-bold text-rose-800 transition hover:border-rose-500 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!isConfirmed || isDeleting}
        onClick={onDelete}
        type="button"
      >
        {isDeleting ? "삭제 중" : "이 프로젝트를 영구 삭제"}
      </button>

      {deleteError && (
        <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
          {deleteError}
        </p>
      )}
    </aside>
  );
}

function ProjectForm({
  form,
  mode,
  onChange,
  onSubmit,
  submitMessage,
  submitState
}: {
  form: ProjectFormState;
  mode: ProjectFormMode;
  onChange: (form: ProjectFormState) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitMessage: string | null;
  submitState: SubmitState;
}) {
  return (
    <form
      className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60"
      onSubmit={onSubmit}
    >
      <div>
        <h2 className="text-2xl font-bold text-slate-900">
          {mode === "create" ? "새 프로젝트 정보" : "프로젝트 정보"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          외부에서 접근 가능한 서비스 주소를 입력하세요. localhost나 사설 IP 같은 내부
          주소는 등록할 수 없습니다.
        </p>
      </div>

      <div className="mt-6 grid gap-4">
        <TextField
          label="프로젝트 이름"
          name="name"
          onChange={(value) => onChange({ ...form, name: value })}
          placeholder="AIM Website"
          required
          value={form.name}
        />
        <TextField
          label="서비스 URL"
          name="service_url"
          onChange={(value) => onChange({ ...form, serviceUrl: value })}
          placeholder="https://example.com"
          required
          value={form.serviceUrl}
        />

        <label className="block" htmlFor="environment">
          <span className="text-sm font-semibold text-slate-600">환경</span>
          <select
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
            id="environment"
            onChange={(event) =>
              onChange({
                ...form,
                environment: event.target.value as ProjectEnvironment
              })
            }
            value={form.environment}
          >
            <option value="development">개발</option>
            <option value="staging">스테이징</option>
            <option value="production">운영</option>
          </select>
        </label>

        <label className="block" htmlFor="description">
          <span className="text-sm font-semibold text-slate-600">설명</span>
          <textarea
            className="mt-2 min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
            id="description"
            maxLength={1000}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
            placeholder="서비스 목적이나 운영 환경을 적어두면 이후 결과 해석에 도움이 됩니다."
            value={form.description}
          />
        </label>

        <div className="grid gap-4 md:grid-cols-3">
          <TextField
            label="검사 주기"
            name="scan_interval_minutes"
            onChange={(value) => onChange({ ...form, scanIntervalMinutes: value })}
            placeholder="60"
            suffix="분"
            type="number"
            value={form.scanIntervalMinutes}
          />
          <TextField
            label="응답 임계값"
            name="response_time_threshold_ms"
            onChange={(value) => onChange({ ...form, responseTimeThresholdMs: value })}
            placeholder="2000"
            suffix="ms"
            type="number"
            value={form.responseTimeThresholdMs}
          />
          <TextField
            label="품질 임계값"
            name="quality_score_threshold"
            onChange={(value) => onChange({ ...form, qualityScoreThreshold: value })}
            placeholder="80"
            suffix="점"
            type="number"
            value={form.qualityScoreThreshold}
          />
        </div>

        <label
          className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4"
          htmlFor="scheduled_scans_enabled"
        >
          <input
            checked={form.scheduledScansEnabled}
            className="mt-1 h-4 w-4 accent-cyan-600"
            id="scheduled_scans_enabled"
            name="scheduled_scans_enabled"
            onChange={(event) =>
              onChange({ ...form, scheduledScansEnabled: event.target.checked })
            }
            type="checkbox"
          />
          <span>
            <span className="block text-sm font-semibold text-slate-700">정기 검사 사용</span>
            <span className="mt-1 block text-xs leading-5 text-slate-500">
              체크하면 인증된 상태에서 위 검사 주기로 자동 검사합니다. 기본은 수동 검사
              전용입니다.
            </span>
          </span>
        </label>
      </div>

      <button
        className="mt-6 w-full rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={submitState === "submitting"}
        type="submit"
      >
        {submitState === "submitting"
          ? "저장 중"
          : mode === "create"
            ? "프로젝트 생성"
            : "프로젝트 저장"}
      </button>

      {submitMessage && (
        <StatusMessage
          message={submitMessage}
          tone={submitState === "success" ? "success" : "danger"}
        />
      )}
    </form>
  );
}

function VerificationPanel({
  onVerify,
  project,
  verification,
  verificationState,
  verifyActionState
}: {
  onVerify: () => void;
  project: Project;
  verification: ProjectVerification | null;
  verificationState: VerificationState;
  verifyActionState: VerifyActionState;
}) {
  return (
    <aside className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">도메인 인증</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            정기 검사를 안전하게 실행하기 전, 대상 서비스를 제어할 수 있는지 확인합니다.
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
            project.is_verified
              ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
              : "bg-amber-50 text-amber-700 ring-amber-200"
          }`}
        >
          {project.is_verified ? "인증됨" : "미인증"}
        </span>
      </div>

      <div className="mt-6 space-y-4">
        <VerificationContent verification={verification} verificationState={verificationState} />

        <button
          className="w-full rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={verificationState !== "success" || verifyActionState === "verifying"}
          onClick={onVerify}
          type="button"
        >
          {verifyActionState === "verifying" ? "확인 중" : "Meta 태그 확인"}
        </button>

        <VerifyActionNotice verifyActionState={verifyActionState} />
      </div>
    </aside>
  );
}

function VerificationContent({
  verification,
  verificationState
}: {
  verification: ProjectVerification | null;
  verificationState: VerificationState;
}) {
  if (verificationState === "loading" || verificationState === "idle") {
    return <Notice description="인증 토큰을 불러오는 중입니다." title="확인 준비 중" />;
  }

  if (verificationState === "unauthorized") {
    return (
      <Notice
        description="로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요."
        title="인증 실패"
        tone="danger"
      />
    );
  }

  if (verificationState === "not-found") {
    return (
      <Notice
        description="프로젝트를 찾을 수 없습니다. 대시보드에서 다시 접근하세요."
        title="프로젝트 없음"
        tone="danger"
      />
    );
  }

  if (verificationState === "unavailable" || !verification) {
    return (
      <Notice
        description="인증 정보를 불러오지 못했습니다. 잠시 후 다시 시도하세요."
        title="인증 정보 요청 실패"
        tone="danger"
      />
    );
  }

  return (
    <div className="space-y-4">
      <Notice
        description="아래 meta 태그를 대상 서비스의 HTML head에 추가하고 배포한 뒤 확인 버튼을 누르세요."
        title={verification.is_verified ? "도메인 인증 완료" : "Meta 태그 설치 필요"}
        tone={verification.is_verified ? "success" : "info"}
      />

      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          Meta 태그
        </p>
        <pre className="mt-2 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-4 text-xs leading-6 text-cyan-700">
          {verification.meta_tag}
        </pre>
      </div>

      <dl className="grid gap-3 text-sm">
        <Metric label="인증 시각" value={formatNullableDateTime(verification.verified_at)} />
      </dl>
    </div>
  );
}

function CreationGuide() {
  return (
    <aside className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60">
      <h2 className="text-2xl font-bold text-slate-900">생성 후 다음 단계</h2>
      <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm leading-6 text-slate-500">
        <li>프로젝트 생성이 완료되면 설정 화면으로 이동합니다.</li>
        <li>AIM이 생성한 HTML meta 태그를 대상 서비스의 head에 추가합니다.</li>
        <li>배포 후 Meta 태그 확인 버튼으로 도메인 소유권을 검증합니다.</li>
        <li>인증된 프로젝트부터 정기 검사 대상이 됩니다.</li>
      </ol>
    </aside>
  );
}

function LoadStateNotice({ loadState }: { loadState: LoadState }) {
  if (loadState === "ready") {
    return null;
  }

  if (loadState === "checking-auth" || loadState === "loading") {
    return <Notice description="로그인 세션과 프로젝트 정보를 확인하는 중입니다." title="불러오는 중" />;
  }

  if (loadState === "unauthorized") {
    return <LoginRequiredNotice />;
  }

  if (loadState === "not-found") {
    return (
      <Notice
        description="요청한 프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요."
        title="프로젝트 없음"
        tone="danger"
      />
    );
  }

  return (
    <Notice
      description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
      title="프로젝트 요청 실패"
      tone="danger"
    />
  );
}

function VerifyActionNotice({ verifyActionState }: { verifyActionState: VerifyActionState }) {
  if (verifyActionState === "idle" || verifyActionState === "verifying") {
    return null;
  }

  if (verifyActionState === "success") {
    return (
      <StatusMessage
        message="Domain ownership이 확인되었습니다."
        tone="success"
      />
    );
  }

  if (verifyActionState === "verification-failed") {
    return (
      <StatusMessage
        message="Target service에서 AIM meta tag를 확인하지 못했습니다. 배포 상태와 service URL을 확인하세요."
        tone="danger"
      />
    );
  }

  return <StatusMessage message={verificationActionMessage[verifyActionState]} tone="danger" />;
}

function TextField({
  label,
  name,
  onChange,
  placeholder,
  required = false,
  suffix,
  type = "text",
  value
}: {
  label: string;
  name: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
  suffix?: string;
  type?: "number" | "text";
  value: string;
}) {
  return (
    <label className="block" htmlFor={name}>
      <span className="text-sm font-semibold text-slate-600">{label}</span>
      <div className="mt-2 flex overflow-hidden rounded-2xl border border-slate-200 bg-white ring-cyan-300/0 transition focus-within:border-cyan-500 focus-within:ring-4 focus-within:ring-cyan-500/20">
        <input
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400"
          id={name}
          min={type === "number" ? 0 : undefined}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          required={required}
          type={type}
          value={value}
        />
        {suffix && (
          <span className="border-l border-slate-200 px-3 py-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
            {suffix}
          </span>
        )}
      </div>
    </label>
  );
}

function StatusMessage({
  message,
  tone
}: {
  message: string;
  tone: "success" | "danger";
}) {
  return (
    <p
      className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
        tone === "success"
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-rose-200 bg-rose-50 text-rose-800"
      }`}
    >
      {message}
    </p>
  );
}

function formFromProject(project: Project): ProjectFormState {
  return {
    name: project.name,
    serviceUrl: project.service_url,
    description: project.description ?? "",
    environment: project.environment,
    scanIntervalMinutes: String(project.scan_interval_minutes),
    scheduledScansEnabled: project.scheduled_scans_enabled,
    responseTimeThresholdMs: String(project.response_time_threshold_ms),
    qualityScoreThreshold: String(project.quality_score_threshold)
  };
}

function buildProjectPayload(
  form: ProjectFormState
): { ok: true; payload: ProjectPayload } | { ok: false; message: string } {
  const name = form.name.trim();
  const serviceUrl = form.serviceUrl.trim();
  const description = form.description.trim();

  if (!name) {
    return { ok: false, message: "Project name을 입력하세요." };
  }

  if (!isHttpUrl(serviceUrl)) {
    return { ok: false, message: "Service URL은 http 또는 https URL이어야 합니다." };
  }

  const scanIntervalMinutes = parseIntegerInRange(form.scanIntervalMinutes, 1, 43_200);
  if (scanIntervalMinutes === null) {
    return { ok: false, message: "Scan interval은 1분 이상 43,200분 이하의 정수여야 합니다." };
  }

  const responseTimeThresholdMs = parseIntegerInRange(form.responseTimeThresholdMs, 1, 600_000);
  if (responseTimeThresholdMs === null) {
    return {
      ok: false,
      message: "Response threshold는 1ms 이상 600,000ms 이하의 정수여야 합니다."
    };
  }

  const qualityScoreThreshold = parseIntegerInRange(form.qualityScoreThreshold, 0, 100);
  if (qualityScoreThreshold === null) {
    return { ok: false, message: "Quality threshold는 0 이상 100 이하의 정수여야 합니다." };
  }

  return {
    ok: true,
    payload: {
      name,
      service_url: serviceUrl,
      description: description || null,
      environment: form.environment,
      scan_interval_minutes: scanIntervalMinutes,
      scheduled_scans_enabled: form.scheduledScansEnabled,
      response_time_threshold_ms: responseTimeThresholdMs,
      quality_score_threshold: qualityScoreThreshold
    }
  };
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function parseIntegerInRange(value: string, min: number, max: number): number | null {
  const parsed = Number(value);

  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    return null;
  }

  return parsed;
}

const projectMutationMessage: Record<Exclude<SubmitState, "idle" | "submitting" | "success">, string> = {
  invalid:
    "프로젝트 정보를 저장하지 못했습니다. URL이 허용되지 않았거나 입력값이 범위를 벗어났습니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요.",
  unavailable: "저장에 실패했습니다. 잠시 후 다시 시도하세요."
};

const verificationActionMessage: Record<
  Exclude<VerifyActionState, "idle" | "verifying" | "success" | "verification-failed">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요.",
  unavailable: "인증 요청에 실패했습니다. 잠시 후 다시 시도하세요."
};
