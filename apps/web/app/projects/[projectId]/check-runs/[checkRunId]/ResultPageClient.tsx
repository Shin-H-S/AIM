"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCheckRunDetail,
  getApiBaseUrl,
  type AvailabilityResult,
  type CheckRunDetail,
  type CheckRunDetailResult,
  type CheckRunStatus,
  type LighthouseResult,
  type SslResult
} from "@/lib/api";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);

const statusLabels: Record<CheckRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

export function ResultPageClient({
  projectId,
  checkRunId
}: {
  projectId: string;
  checkRunId: string;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<CheckRunDetailResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();
  const checkRun = result?.state === "success" ? result.checkRun : null;
  const shouldPoll = checkRun ? ACTIVE_STATUSES.has(checkRun.status) : false;

  const refresh = useCallback(async () => {
    if (!trimmedToken) {
      setResult(null);
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchCheckRunDetail({
      projectId,
      checkRunId,
      accessToken: trimmedToken
    });
    setResult(nextResult);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [checkRunId, projectId, trimmedToken]);

  useEffect(() => {
    if (!shouldPoll || !trimmedToken) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [refresh, shouldPoll, trimmedToken]);

  const apiBaseUrlLabel = useMemo(() => {
    try {
      return getApiBaseUrl();
    } catch {
      return "잘못된 NEXT_PUBLIC_API_URL";
    }
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6 rounded-3xl border border-white/10 bg-white/[0.03] p-6">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-300">
              AIM Scan Result
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
              CheckRun 결과
            </h1>
            <p className="mt-4 text-sm leading-6 text-slate-300">
              이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의 CheckRun 단건
              API를 polling해서 상태와 저장된 scanner result를 보여줍니다.
            </p>
          </div>

          <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
            <Identifier label="Project ID" value={projectId} />
            <Identifier label="CheckRun ID" value={checkRunId} />
          </div>

          <form
            className="grid gap-3 md:grid-cols-[1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void refresh();
            }}
          >
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium text-slate-200">Bearer token</span>
              <input
                className="rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none ring-cyan-400/0 transition focus:border-cyan-300 focus:ring-4 focus:ring-cyan-400/10"
                type="password"
                value={accessToken}
                placeholder="로그인 API에서 받은 access_token을 입력하세요"
                onChange={(event) => setAccessToken(event.target.value)}
              />
            </label>
            <button
              className="self-end rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              type="submit"
              disabled={!trimmedToken || isLoading}
            >
              {isLoading ? "조회 중" : "결과 조회"}
            </button>
          </form>
        </header>

        {!trimmedToken && (
          <Notice
            tone="info"
            title="인증 토큰이 필요합니다"
            description="현재 웹에는 로그인 UI가 없으므로, API 로그인 응답의 access_token을 직접 입력해야 합니다."
          />
        )}

        {result?.state === "unauthorized" && (
          <Notice
            tone="danger"
            title="인증 실패"
            description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
          />
        )}

        {result?.state === "not-found" && (
          <Notice
            tone="danger"
            title="CheckRun을 찾을 수 없습니다"
            description="Project ID, CheckRun ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="API 요청 실패"
            description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
          />
        )}

        {checkRun && (
          <>
            <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <StatusSummary
                checkRun={checkRun}
                shouldPoll={shouldPoll}
                lastUpdatedAt={lastUpdatedAt}
              />
              <TimelineCard checkRun={checkRun} />
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <AvailabilityCard result={checkRun.availability_result} />
              <SslCard result={checkRun.ssl_result} />
              <LighthouseCard result={checkRun.lighthouse_result} />
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </p>
      <p className="break-all font-mono text-xs text-slate-200">{value}</p>
    </div>
  );
}

function StatusSummary({
  checkRun,
  shouldPoll,
  lastUpdatedAt
}: {
  checkRun: CheckRunDetail;
  shouldPoll: boolean;
  lastUpdatedAt: string | null;
}) {
  const badgeClassName = getStatusBadgeClassName(checkRun.status);

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${badgeClassName}`}>
          {statusLabels[checkRun.status]}
        </span>
      </div>
      <dl className="grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Trigger" value={checkRun.trigger_source} />
        <Metric label="Polling" value={shouldPoll ? "자동 새로고침 중" : "중지됨"} />
        <Metric label="Failure" value={checkRun.failure_reason ?? "없음"} />
        <Metric label="Last refresh" value={lastUpdatedAt ?? "아직 없음"} />
      </dl>
    </article>
  );
}

function TimelineCard({ checkRun }: { checkRun: CheckRunDetail }) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="mb-5 text-xl font-semibold">타임라인</h2>
      <dl className="grid gap-4 text-sm text-slate-300">
        <Metric label="Queued" value={formatDateTime(checkRun.queued_at)} />
        <Metric label="Started" value={formatDateTime(checkRun.started_at)} />
        <Metric label="Finished" value={formatDateTime(checkRun.finished_at)} />
        <Metric label="Updated" value={formatDateTime(checkRun.updated_at)} />
      </dl>
    </article>
  );
}

function AvailabilityCard({ result }: { result: AvailabilityResult | null }) {
  if (!result) {
    return <EmptyResultCard title="Availability" description="아직 availability 결과가 없습니다." />;
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="Availability"
        isHealthy={result.is_available}
        healthyLabel="사용 가능"
        unhealthyLabel="사용 불가"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Status code" value={formatNullable(result.status_code)} />
        <Metric label="Response time" value={formatMilliseconds(result.response_time_ms)} />
        <Metric label="Redirects" value={String(result.redirect_count)} />
        <Metric label="HTTPS" value={result.uses_https ? "사용" : "미사용"} />
        <Metric label="Timed out" value={result.timed_out ? "예" : "아니오"} />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">
        Final URL: {result.final_url ?? "없음"}
      </p>
    </article>
  );
}

function SslCard({ result }: { result: SslResult | null }) {
  if (!result) {
    return <EmptyResultCard title="SSL" description="아직 SSL inspection 결과가 없습니다." />;
  }

  const isHealthy = result.is_applicable ? result.is_valid === true : true;

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="SSL"
        isHealthy={isHealthy}
        healthyLabel={result.is_applicable ? "유효" : "대상 아님"}
        unhealthyLabel="문제 있음"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Applicable" value={result.is_applicable ? "예" : "아니오"} />
        <Metric label="Valid" value={formatBoolean(result.is_valid)} />
        <Metric label="Expires at" value={formatDateTime(result.expires_at)} />
        <Metric
          label="Days left"
          value={
            result.days_until_expiration === null
              ? "알 수 없음"
              : `${result.days_until_expiration}일`
          }
        />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">Service URL: {result.service_url}</p>
    </article>
  );
}

function LighthouseCard({ result }: { result: LighthouseResult | null }) {
  if (!result) {
    return (
      <EmptyResultCard title="Lighthouse" description="아직 Lighthouse 결과가 없습니다." />
    );
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="Lighthouse"
        isHealthy={result.is_successful}
        healthyLabel="실행 성공"
        unhealthyLabel="실행 실패"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Performance" value={formatScore(result.performance_score)} />
        <Metric label="Accessibility" value={formatScore(result.accessibility_score)} />
        <Metric label="SEO" value={formatScore(result.seo_score)} />
        <Metric label="Best practices" value={formatScore(result.best_practices_score)} />
        <Metric label="LCP" value={formatMilliseconds(result.largest_contentful_paint_ms)} />
        <Metric label="CLS" value={formatDecimal(result.cumulative_layout_shift)} />
        <Metric label="TBT" value={formatMilliseconds(result.total_blocking_time_ms)} />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">Service URL: {result.service_url}</p>
    </article>
  );
}

function EmptyResultCard({ title, description }: { title: string; description: string }) {
  return (
    <article className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-4 text-sm text-slate-400">{description}</p>
    </article>
  );
}

function ResultHeader({
  title,
  isHealthy,
  healthyLabel,
  unhealthyLabel
}: {
  title: string;
  isHealthy: boolean;
  healthyLabel: string;
  unhealthyLabel: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      <span
        className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
          isHealthy
            ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
            : "bg-rose-400/10 text-rose-300 ring-rose-400/20"
        }`}
      >
        {isHealthy ? healthyLabel : unhealthyLabel}
      </span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-200">{value}</dd>
    </div>
  );
}

function Notice({
  tone,
  title,
  description
}: {
  tone: "info" | "danger";
  title: string;
  description: string;
}) {
  const className =
    tone === "info"
      ? "border-cyan-400/20 bg-cyan-400/10 text-cyan-100"
      : "border-rose-400/20 bg-rose-400/10 text-rose-100";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm opacity-80">{description}</p>
    </article>
  );
}

function getStatusBadgeClassName(status: CheckRunStatus) {
  if (status === "COMPLETED") {
    return "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";
  }

  if (status === "FAILED" || status === "CANCELLED") {
    return "bg-rose-400/10 text-rose-300 ring-rose-400/20";
  }

  return "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20";
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "없음";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(new Date(value));
}

function formatMilliseconds(value: number | null) {
  return value === null ? "알 수 없음" : `${value}ms`;
}

function formatNullable(value: number | null) {
  return value === null ? "없음" : String(value);
}

function formatScore(value: number | null) {
  return value === null ? "알 수 없음" : `${value}/100`;
}

function formatDecimal(value: number | null) {
  return value === null ? "알 수 없음" : String(value);
}

function formatBoolean(value: boolean | null) {
  if (value === null) {
    return "대상 아님";
  }

  return value ? "예" : "아니오";
}
