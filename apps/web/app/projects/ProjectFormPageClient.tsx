"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createProject,
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

type ProjectFormMode = "create" | "edit";

type ProjectFormState = {
  name: string;
  serviceUrl: string;
  description: string;
  environment: ProjectEnvironment;
  scanIntervalMinutes: string;
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
  const [accessToken, setAccessToken] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectFormState>(initialForm);
  const [loadState, setLoadState] = useState<LoadState>("checking-auth");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [verification, setVerification] = useState<ProjectVerification | null>(null);
  const [verificationState, setVerificationState] = useState<VerificationState>("idle");
  const [verifyActionState, setVerifyActionState] = useState<VerifyActionState>("idle");

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

      setAccessToken(storedAccessToken);

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
        ? "Project를 생성했습니다. Domain verification 안내로 이동합니다."
        : "Project 설정을 저장했습니다."
    );

    if (mode === "create") {
      router.replace(`/projects/${result.project.id}/settings`);
      return;
    }

    await loadVerification(accessToken, result.project.id);
  }

  async function handleVerifyProject() {
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

  const title = mode === "create" ? "Project 생성" : "Project 설정";
  const subtitle =
    mode === "create"
      ? "서비스 URL과 검사 기준을 등록합니다. 생성 후 HTML meta-tag 기반 domain verification 안내로 이동합니다."
      : "서비스 URL, 환경, 검사 기준을 수정하고 domain verification 상태를 확인합니다.";

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <div>
          <Link
            className="inline-flex rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
            href="/"
          >
            Dashboard로 돌아가기
          </Link>
          <p className="mt-8 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
            AIM Project Management
          </p>
          <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-6xl">{title}</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-300">{subtitle}</p>
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
              <VerificationPanel
                onVerify={handleVerifyProject}
                project={project}
                verification={verification}
                verificationState={verificationState}
                verifyActionState={verifyActionState}
              />
            ) : (
              <CreationGuide />
            )}
          </div>
        )}
      </section>
    </main>
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
      className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20"
      onSubmit={onSubmit}
    >
      <div>
        <h2 className="text-2xl font-bold text-slate-100">
          {mode === "create" ? "새 Project 정보" : "Project 정보"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          URL은 서버에서 SSRF-safe validation을 다시 수행합니다. localhost, private IP,
          cloud metadata endpoint 같은 내부 주소는 등록할 수 없습니다.
        </p>
      </div>

      <div className="mt-6 grid gap-4">
        <TextField
          label="Project name"
          name="name"
          onChange={(value) => onChange({ ...form, name: value })}
          placeholder="AIM Website"
          required
          value={form.name}
        />
        <TextField
          label="Service URL"
          name="service_url"
          onChange={(value) => onChange({ ...form, serviceUrl: value })}
          placeholder="https://example.com"
          required
          value={form.serviceUrl}
        />

        <label className="block" htmlFor="environment">
          <span className="text-sm font-semibold text-slate-300">Environment</span>
          <select
            className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
            id="environment"
            onChange={(event) =>
              onChange({
                ...form,
                environment: event.target.value as ProjectEnvironment
              })
            }
            value={form.environment}
          >
            <option value="development">development</option>
            <option value="staging">staging</option>
            <option value="production">production</option>
          </select>
        </label>

        <label className="block" htmlFor="description">
          <span className="text-sm font-semibold text-slate-300">Description</span>
          <textarea
            className="mt-2 min-h-28 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
            id="description"
            maxLength={1000}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
            placeholder="서비스 목적이나 운영 환경을 적어두면 이후 결과 해석에 도움이 됩니다."
            value={form.description}
          />
        </label>

        <div className="grid gap-4 md:grid-cols-3">
          <TextField
            label="Scan interval"
            name="scan_interval_minutes"
            onChange={(value) => onChange({ ...form, scanIntervalMinutes: value })}
            placeholder="60"
            suffix="minutes"
            type="number"
            value={form.scanIntervalMinutes}
          />
          <TextField
            label="Response threshold"
            name="response_time_threshold_ms"
            onChange={(value) => onChange({ ...form, responseTimeThresholdMs: value })}
            placeholder="2000"
            suffix="ms"
            type="number"
            value={form.responseTimeThresholdMs}
          />
          <TextField
            label="Quality threshold"
            name="quality_score_threshold"
            onChange={(value) => onChange({ ...form, qualityScoreThreshold: value })}
            placeholder="80"
            suffix="score"
            type="number"
            value={form.qualityScoreThreshold}
          />
        </div>
      </div>

      <button
        className="mt-6 w-full rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={submitState === "submitting"}
        type="submit"
      >
        {submitState === "submitting"
          ? "저장 중"
          : mode === "create"
            ? "Project 생성"
            : "Project 저장"}
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
    <aside className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Domain verification</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            recurring scan을 안전하게 실행하기 전, target service를 제어할 수 있는지 확인합니다.
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
            project.is_verified
              ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
              : "bg-amber-400/10 text-amber-300 ring-amber-400/20"
          }`}
        >
          {project.is_verified ? "verified" : "unverified"}
        </span>
      </div>

      <div className="mt-6 space-y-4">
        <VerificationContent verification={verification} verificationState={verificationState} />

        <button
          className="w-full rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={verificationState !== "success" || verifyActionState === "verifying"}
          onClick={onVerify}
          type="button"
        >
          {verifyActionState === "verifying" ? "확인 중" : "Meta tag 확인"}
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
    return <Notice description="Verification token을 불러오는 중입니다." title="확인 준비 중" />;
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
        description="Project를 찾을 수 없습니다. Dashboard에서 다시 접근하세요."
        title="Project 없음"
        tone="danger"
      />
    );
  }

  if (verificationState === "unavailable" || !verification) {
    return (
      <Notice
        description="Verification 정보를 불러오지 못했습니다. API 서버 상태를 확인하세요."
        title="Verification 요청 실패"
        tone="danger"
      />
    );
  }

  return (
    <div className="space-y-4">
      <Notice
        description="아래 meta tag를 target service의 HTML head에 추가하고 배포한 뒤 확인 버튼을 누르세요."
        title={verification.is_verified ? "Domain verified" : "Meta tag 설치 필요"}
        tone={verification.is_verified ? "success" : "info"}
      />

      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Meta tag
        </p>
        <pre className="mt-2 overflow-x-auto rounded-2xl border border-white/10 bg-slate-950 p-4 text-xs leading-6 text-cyan-100">
          {verification.meta_tag}
        </pre>
      </div>

      <dl className="grid gap-3 text-sm">
        <Metric label="Verification token" value={verification.verification_token} />
        <Metric label="Verified at" value={verification.verified_at ?? "아직 없음"} />
      </dl>
    </div>
  );
}

function CreationGuide() {
  return (
    <aside className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20">
      <h2 className="text-2xl font-bold text-slate-100">생성 후 다음 단계</h2>
      <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm leading-6 text-slate-400">
        <li>Project 생성이 완료되면 settings 화면으로 이동합니다.</li>
        <li>AIM이 생성한 HTML meta tag를 target service의 head에 추가합니다.</li>
        <li>배포 후 Meta tag 확인 버튼으로 domain ownership을 검증합니다.</li>
        <li>검증된 Project부터 recurring scan 대상이 됩니다.</li>
      </ol>
    </aside>
  );
}

function LoadStateNotice({ loadState }: { loadState: LoadState }) {
  if (loadState === "ready") {
    return null;
  }

  if (loadState === "checking-auth" || loadState === "loading") {
    return <Notice description="로그인 세션과 Project 정보를 확인하는 중입니다." title="불러오는 중" />;
  }

  if (loadState === "unauthorized") {
    return (
      <Notice
        description="Project를 관리하려면 먼저 로그인해야 합니다."
        title="로그인 필요"
        tone="danger"
      />
    );
  }

  if (loadState === "not-found") {
    return (
      <Notice
        description="요청한 Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요."
        title="Project 없음"
        tone="danger"
      />
    );
  }

  return (
    <Notice
      description="API 서버 상태와 NEXT_PUBLIC_API_URL 설정을 확인한 뒤 다시 시도하세요."
      title="Project 요청 실패"
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
      <span className="text-sm font-semibold text-slate-300">{label}</span>
      <div className="mt-2 flex overflow-hidden rounded-2xl border border-white/10 bg-slate-950 ring-cyan-300/0 transition focus-within:border-cyan-300/60 focus-within:ring-4 focus-within:ring-cyan-300/10">
        <input
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
          id={name}
          min={type === "number" ? 0 : undefined}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          required={required}
          type={type}
          value={value}
        />
        {suffix && (
          <span className="border-l border-white/10 px-3 py-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
            {suffix}
          </span>
        )}
      </div>
    </label>
  );
}

function Notice({
  description,
  title,
  tone = "info"
}: {
  description: string;
  title: string;
  tone?: "info" | "danger" | "success";
}) {
  const className =
    tone === "danger"
      ? "border-rose-400/20 bg-rose-400/10 text-rose-100"
      : tone === "success"
        ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
        : "border-cyan-300/20 bg-cyan-300/10 text-cyan-100";

  return (
    <div className={`rounded-2xl border p-4 ${className}`}>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 opacity-85">{description}</p>
    </div>
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
          ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
          : "border-rose-400/20 bg-rose-400/10 text-rose-100"
      }`}
    >
      {message}
    </p>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-all text-slate-200">{value}</dd>
    </div>
  );
}

function formFromProject(project: Project): ProjectFormState {
  return {
    name: project.name,
    serviceUrl: project.service_url,
    description: project.description ?? "",
    environment: project.environment,
    scanIntervalMinutes: String(project.scan_interval_minutes),
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
    "Project 정보를 저장하지 못했습니다. URL이 허용되지 않았거나 입력값이 범위를 벗어났습니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
  unavailable: "API 서버 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
};

const verificationActionMessage: Record<
  Exclude<VerifyActionState, "idle" | "verifying" | "success" | "verification-failed">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
  unavailable: "Verification 요청에 실패했습니다. API 서버 상태를 확인하세요."
};
