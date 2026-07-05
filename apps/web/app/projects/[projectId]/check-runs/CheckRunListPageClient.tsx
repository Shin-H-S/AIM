"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCheckRuns,
  getApiBaseUrl,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";

const LIST_LIMIT = 20;

const statusLabels: Record<CheckRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

type CheckRunListSummary = {
  total: number;
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
};

export function CheckRunListPageClient({ projectId }: { projectId: string }) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<CheckRunListResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreCheckRuns, setHasMoreCheckRuns] = useState(false);
  const [listMessage, setListMessage] = useState<string | null>(null);
  const [hasCheckedStoredToken, setHasCheckedStoredToken] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();
  const checkRuns = result?.state === "success" ? result.checkRuns : [];
  const summary = summarizeCheckRuns(checkRuns);

  const loadCheckRuns = useCallback(
    async (token: string) => {
      const normalizedToken = token.trim();

      if (!normalizedToken) {
        setResult(null);
        setHasMoreCheckRuns(false);
        setIsLoadingMore(false);
        setListMessage(null);
        setLastUpdatedAt(null);
        return;
      }

      setIsLoading(true);
      setListMessage(null);
      const nextResult = await fetchCheckRuns({
        projectId,
        accessToken: normalizedToken,
        limit: LIST_LIMIT
      });

      if (nextResult.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(normalizedToken);
      }

      setResult(nextResult);
      setHasMoreCheckRuns(
        nextResult.state === "success" && nextResult.checkRuns.length === LIST_LIMIT
      );
      setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
      setIsLoading(false);
    },
    [projectId]
  );

  const refresh = useCallback(async () => {
    await loadCheckRuns(trimmedToken);
  }, [loadCheckRuns, trimmedToken]);

  async function handleLoadMoreCheckRuns() {
    if (!trimmedToken || result?.state !== "success" || isLoadingMore) {
      return;
    }

    setIsLoadingMore(true);
    setListMessage(null);

    const nextResult = await fetchCheckRuns({
      projectId,
      accessToken: trimmedToken,
      limit: LIST_LIMIT,
      offset: result.checkRuns.length
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(trimmedToken);
    }

    if (nextResult.state !== "success") {
      setListMessage(checkRunListMessageByState[nextResult.state]);
      setIsLoadingMore(false);
      return;
    }

    setResult((current) =>
      current?.state === "success"
        ? {
            state: "success",
            checkRuns: [...current.checkRuns, ...nextResult.checkRuns]
          }
        : nextResult
    );
    setHasMoreCheckRuns(nextResult.checkRuns.length === LIST_LIMIT);

    if (nextResult.checkRuns.length === 0) {
      setListMessage("더 불러올 CheckRun이 없습니다.");
    }

    setIsLoadingMore(false);
  }

  useEffect(() => {
    const storedAccessToken = getStoredAccessToken();

    queueMicrotask(() => {
      setHasCheckedStoredToken(true);

      if (!storedAccessToken) {
        return;
      }

      setAccessToken(storedAccessToken);
      void loadCheckRuns(storedAccessToken);
    });
  }, [loadCheckRuns]);

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
        <header className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-300">
                AIM Check Runs
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                CheckRun 이력
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">
                이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>에서 이
                Project의 전체 CheckRun 이력을 조회합니다. 결과 페이지에서 점수, baseline
                비교, AI 진단을 확인할 수 있습니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                className="rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
                href={`/projects/${projectId}/settings`}
              >
                Project 설정
              </Link>
              <Link
                className="rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
                href="/"
              >
                Dashboard
              </Link>
            </div>
          </div>

          <div className="mt-5 grid gap-3 text-sm text-slate-300 md:grid-cols-2">
            <Identifier label="Project ID" value={projectId} />
            <Identifier label="Page size" value={`${LIST_LIMIT}개`} />
          </div>

          <form
            className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void refresh();
            }}
          >
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium text-slate-200">Bearer token</span>
              <input
                className="rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none ring-cyan-400/0 transition focus:border-cyan-300 focus:ring-4 focus:ring-cyan-400/10"
                onChange={(event) => setAccessToken(event.target.value)}
                placeholder="로그인 API에서 받은 access_token을 입력하세요"
                type="password"
                value={accessToken}
              />
            </label>
            <button
              className="self-end rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!trimmedToken || isLoading}
              type="submit"
            >
              {isLoading ? "조회 중" : "CheckRun 조회"}
            </button>
          </form>
        </header>

        {!hasCheckedStoredToken && (
          <Notice
            description="저장된 로그인 세션이 있으면 자동으로 CheckRun 이력을 조회합니다."
            title="로그인 세션 확인 중"
            tone="info"
          />
        )}

        {hasCheckedStoredToken && !trimmedToken && (
          <Notice
            description="로그인 페이지에서 먼저 로그인하거나 access token을 직접 입력하세요."
            title="인증 토큰이 필요합니다"
            tone="info"
          />
        )}

        {result?.state === "unauthorized" && (
          <Notice
            description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
            title="인증 실패"
            tone="danger"
          />
        )}

        {result?.state === "not-found" && (
          <Notice
            description="Project ID 또는 현재 사용자 권한을 확인하세요."
            title="CheckRun 이력을 찾을 수 없습니다"
            tone="danger"
          />
        )}

        {result?.state === "unavailable" && (
          <Notice
            description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
            title="API 요청 실패"
            tone="danger"
          />
        )}

        {result?.state === "success" && (
          <>
            <SummaryCard lastUpdatedAt={lastUpdatedAt} summary={summary} />
            <CheckRunList
              checkRuns={checkRuns}
              hasMoreCheckRuns={hasMoreCheckRuns}
              isLoadingMore={isLoadingMore}
              listMessage={listMessage}
              onLoadMore={() => void handleLoadMoreCheckRuns()}
              projectId={projectId}
            />
          </>
        )}
      </section>
    </main>
  );
}

function SummaryCard({
  lastUpdatedAt,
  summary
}: {
  lastUpdatedAt: string | null;
  summary: CheckRunListSummary;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-300">
            최근 실행 요약
          </p>
          <h2 className="mt-3 text-2xl font-bold text-slate-100">
            최근 CheckRun {summary.total}개
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            마지막 조회: {lastUpdatedAt ?? "아직 없음"}
          </p>
        </div>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          로드 {summary.total}개
        </span>
      </div>

      <dl className="mt-6 grid gap-4 md:grid-cols-5">
        <Metric label="Total" value={`${summary.total}개`} />
        <Metric label="Active" value={`${summary.active}개`} />
        <Metric label="Completed" value={`${summary.completed}개`} />
        <Metric label="Failed" value={`${summary.failed}개`} />
        <Metric label="Cancelled" value={`${summary.cancelled}개`} />
      </dl>
    </section>
  );
}

function CheckRunList({
  checkRuns,
  hasMoreCheckRuns,
  isLoadingMore,
  listMessage,
  onLoadMore,
  projectId
}: {
  checkRuns: CheckRunSummary[];
  hasMoreCheckRuns: boolean;
  isLoadingMore: boolean;
  listMessage: string | null;
  onLoadMore: () => void;
  projectId: string;
}) {
  if (checkRuns.length === 0) {
    return (
      <section className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] p-6">
        <h2 className="text-xl font-semibold">CheckRun 없음</h2>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          아직 실행된 CheckRun이 없습니다. Dashboard에서 검사를 시작하면 이곳에 이력이
          기록됩니다.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 이력</h2>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          {checkRuns.length}개
        </span>
      </div>
      <ul className="grid gap-4">
        {checkRuns.map((checkRun) => (
          <CheckRunCard checkRun={checkRun} key={checkRun.id} projectId={projectId} />
        ))}
      </ul>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          className="rounded-2xl border border-cyan-300/30 px-4 py-2 text-sm font-bold text-cyan-100 transition hover:border-cyan-200 hover:bg-cyan-300/10 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreCheckRuns || isLoadingMore}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMore ? "더 불러오는 중" : "CheckRun 더 보기"}
        </button>
        <p className="text-sm text-slate-400">
          {hasMoreCheckRuns
            ? `${LIST_LIMIT}개 단위로 다음 실행 이력을 불러옵니다.`
            : "현재 로드된 목록이 마지막 page입니다."}
        </p>
      </div>

      {listMessage && (
        <p className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4 text-sm text-cyan-100">
          {listMessage}
        </p>
      )}
    </section>
  );
}

function CheckRunCard({
  checkRun,
  projectId
}: {
  checkRun: CheckRunSummary;
  projectId: string;
}) {
  return (
    <li className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={checkRun.status} />
            <Badge label={checkRun.trigger_source} />
          </div>
          <p className="mt-4 break-all font-mono text-xs text-slate-400">{checkRun.id}</p>
        </div>
        <Link
          className="rounded-2xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
          href={`/projects/${projectId}/check-runs/${checkRun.id}`}
        >
          결과 보기
        </Link>
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-3">
        <Metric label="Queued" value={formatDateTime(checkRun.queued_at)} />
        <Metric label="Started" value={formatNullableDateTime(checkRun.started_at)} />
        <Metric label="Finished" value={formatNullableDateTime(checkRun.finished_at)} />
      </dl>

      {checkRun.failure_reason && (
        <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
          {checkRun.failure_reason}
        </p>
      )}
    </li>
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-200">{value}</dd>
    </div>
  );
}

function Notice({
  description,
  title,
  tone
}: {
  description: string;
  title: string;
  tone: "info" | "danger";
}) {
  const className =
    tone === "info"
      ? "border-cyan-400/20 bg-cyan-400/10 text-cyan-100"
      : "border-rose-400/20 bg-rose-400/10 text-rose-100";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 opacity-80">{description}</p>
    </article>
  );
}

function Badge({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-slate-700/80 px-3 py-1 text-xs font-bold text-slate-200 ring-1 ring-white/10">
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: CheckRunStatus }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getStatusBadgeClassName(status)}`}
    >
      {statusLabels[status]}
    </span>
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

function summarizeCheckRuns(checkRuns: CheckRunSummary[]): CheckRunListSummary {
  return checkRuns.reduce<CheckRunListSummary>(
    (summary, checkRun) => {
      summary.total += 1;

      if (
        checkRun.status === "QUEUED" ||
        checkRun.status === "RUNNING" ||
        checkRun.status === "ANALYZING"
      ) {
        summary.active += 1;
      }

      if (checkRun.status === "COMPLETED") {
        summary.completed += 1;
      }

      if (checkRun.status === "FAILED") {
        summary.failed += 1;
      }

      if (checkRun.status === "CANCELLED") {
        summary.cancelled += 1;
      }

      return summary;
    },
    {
      total: 0,
      active: 0,
      completed: 0,
      failed: 0,
      cancelled: 0
    }
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "아직 없음";
}

const checkRunListMessageByState: Record<Exclude<CheckRunListResult["state"], "success">, string> =
  {
    unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
    "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
    unavailable: "CheckRun 이력을 더 불러오지 못했습니다. API 서버 상태를 확인하세요."
  };
