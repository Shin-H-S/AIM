import Link from "next/link";
import type { ReactNode } from "react";
import type { CheckRunStatus, ScenarioRunStatus } from "@/lib/api";

export const checkRunStatusCopy: Record<CheckRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

export const scenarioRunStatusCopy: Record<ScenarioRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

type RunStatus = CheckRunStatus | ScenarioRunStatus;

function getRunStatusBadgeClassName(status: RunStatus): string {
  if (status === "COMPLETED") {
    return "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900";
  }

  if (status === "FAILED") {
    return "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900";
  }

  if (status === "CANCELLED") {
    return "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 ring-slate-300";
  }

  return "bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-400 ring-cyan-200 dark:ring-cyan-900";
}

export function CheckRunStatusBadge({ status }: { status: CheckRunStatus }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getRunStatusBadgeClassName(status)}`}
    >
      {checkRunStatusCopy[status]}
    </span>
  );
}

export function ScenarioRunStatusBadge({ status }: { status: ScenarioRunStatus }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getRunStatusBadgeClassName(status)}`}
    >
      {scenarioRunStatusCopy[status]}
    </span>
  );
}

const badgeToneClassName = {
  default: "bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 ring-slate-200 dark:ring-slate-700",
  success: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900",
  warning: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-900",
  danger: "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
} as const;

export function Badge({
  label,
  tone = "default"
}: {
  label: string;
  tone?: keyof typeof badgeToneClassName;
}) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${badgeToneClassName[tone]}`}>
      {label}
    </span>
  );
}

export function InfoHint({ text }: { text: string }) {
  return (
    <span className="group relative ml-1.5 inline-flex align-middle">
      <span
        aria-label={text}
        className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-slate-300 dark:border-slate-700 text-[9px] font-bold leading-none text-slate-400 dark:text-slate-500 transition group-hover:border-cyan-400 group-hover:text-cyan-600"
        role="img"
        tabIndex={0}
      >
        !
      </span>
      <span className="pointer-events-none invisible absolute bottom-full left-0 z-20 mb-1.5 w-max max-w-60 break-keep rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium normal-case leading-5 tracking-normal text-white opacity-0 transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
        {text}
      </span>
    </span>
  );
}

export function Metric({ hint, label, value }: { hint?: string; label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
        {label}
        {hint && <InfoHint text={hint} />}
      </dt>
      <dd className="mt-1 break-words text-slate-700 dark:text-slate-200">{value}</dd>
    </div>
  );
}

export function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p className="break-all font-mono text-xs text-slate-700 dark:text-slate-200">{value}</p>
    </div>
  );
}

export function Notice({
  action,
  description,
  title,
  tone = "info"
}: {
  action?: ReactNode;
  description: string;
  title: string;
  tone?: "info" | "danger" | "success";
}) {
  const className =
    tone === "danger"
      ? "border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300"
      : tone === "success"
        ? "border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300"
        : "border-cyan-200 dark:border-cyan-900 bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-400";

  return (
    <div className={`rounded-2xl border p-5 ${className}`}>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 opacity-85">{description}</p>
      {action && <div className="mt-4 flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function LoginRequiredNotice({ expired = false }: { expired?: boolean }) {
  return (
    <Notice
      action={
        <Link
          className="inline-flex rounded-xl bg-cyan-700 px-4 py-2 text-xs font-bold text-white transition hover:bg-cyan-600"
          href="/"
        >
          로그인 페이지로 이동
        </Link>
      }
      description={
        expired
          ? "로그인 세션이 만료되었거나 이 리소스에 접근할 권한이 없습니다. 다시 로그인한 뒤 시도하세요."
          : "이 화면은 로그인 후 이용할 수 있습니다. 로그인하면 저장된 세션으로 자동 조회합니다."
      }
      title={expired ? "인증이 만료되었습니다" : "로그인이 필요합니다"}
      tone={expired ? "danger" : "info"}
    />
  );
}

export function EmptyState({
  compact = false,
  description,
  title
}: {
  compact?: boolean;
  description: string;
  title?: string;
}) {
  return (
    <div className={`rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 ${compact ? "p-4" : "p-6"}`}>
      {title && <h3 className="font-semibold text-slate-900 dark:text-white">{title}</h3>}
      <p className={`text-sm leading-6 text-slate-500 dark:text-slate-400 ${title ? "mt-2" : ""}`}>{description}</p>
    </div>
  );
}

const linkButtonVariantClassName = {
  outline:
    "border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 hover:border-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300",
  primary: "bg-cyan-700 text-white hover:bg-cyan-600",
  dark: "bg-slate-900 text-white hover:bg-cyan-600"
} as const;

export function LinkButton({
  href,
  label,
  variant = "outline"
}: {
  href: string;
  label: string;
  variant?: keyof typeof linkButtonVariantClassName;
}) {
  return (
    <Link
      className={`rounded-2xl px-4 py-2 text-sm font-bold transition ${linkButtonVariantClassName[variant]}`}
      href={href}
    >
      {label}
    </Link>
  );
}

export function RefreshButton({
  isLoading,
  label = "새로고침",
  loadingLabel = "불러오는 중",
  onClick
}: {
  isLoading: boolean;
  label?: string;
  loadingLabel?: string;
  onClick: () => void;
}) {
  return (
    <button
      className="rounded-2xl border border-cyan-300 dark:border-cyan-800 px-4 py-2 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950 disabled:cursor-not-allowed disabled:opacity-50"
      disabled={isLoading}
      onClick={onClick}
      type="button"
    >
      {isLoading ? loadingLabel : label}
    </button>
  );
}
