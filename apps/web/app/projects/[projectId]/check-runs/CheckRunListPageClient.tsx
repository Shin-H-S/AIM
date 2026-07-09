"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  fetchCheckRuns,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import { formatDateWithWeekday, formatDuration, formatTimeOfDay } from "@/lib/format";
import { deploymentRiskLabel, triggerSourceLabel } from "@/lib/statusLabels";
import { ScoreTrendPanel } from "@/components/charts";
import { buildScoreTrendSeries, scoredRunCount } from "@/lib/scoreTrend";
import {
  checkRunStatusCopy,
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton
} from "@/components/ui";

const LIST_LIMIT = 20;

type CheckRunListSummary = {
  total: number;
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
};

type CheckRunListPageState =
  | { state: "checking" }
  | { state: "signed-out" }
  | CheckRunListResult;

export function CheckRunListPageClient({ projectId }: { projectId: string }) {
  const [result, setResult] = useState<CheckRunListPageState>({ state: "checking" });
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreCheckRuns, setHasMoreCheckRuns] = useState(false);
  const [listMessage, setListMessage] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const checkRuns = result.state === "success" ? result.checkRuns : [];
  const summary = summarizeCheckRuns(checkRuns);

  const loadCheckRuns = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setResult({ state: "signed-out" });
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
      accessToken,
      limit: LIST_LIMIT
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setResult(nextResult);
    setHasMoreCheckRuns(
      nextResult.state === "success" && nextResult.checkRuns.length === LIST_LIMIT
    );
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [projectId]);

  async function handleLoadMoreCheckRuns() {
    const accessToken = getStoredAccessToken();

    if (!accessToken || result.state !== "success" || isLoadingMore) {
      return;
    }

    setIsLoadingMore(true);
    setListMessage(null);

    const nextResult = await fetchCheckRuns({
      projectId,
      accessToken,
      limit: LIST_LIMIT,
      offset: result.checkRuns.length
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    if (nextResult.state !== "success") {
      setListMessage(checkRunListMessageByState[nextResult.state]);
      setIsLoadingMore(false);
      return;
    }

    setResult((current) =>
      current.state === "success"
        ? {
            state: "success",
            checkRuns: [...current.checkRuns, ...nextResult.checkRuns]
          }
        : nextResult
    );
    setHasMoreCheckRuns(nextResult.checkRuns.length === LIST_LIMIT);

    if (nextResult.checkRuns.length === 0) {
      setListMessage("더 불러올 검사가 없습니다.");
    }

    setIsLoadingMore(false);
  }

  useEffect(() => {
    queueMicrotask(() => {
      void loadCheckRuns();
    });
  }, [loadCheckRuns]);

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="rounded-3xl border border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700">
                AIM 검사
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                검사 이력
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                이 프로젝트의 전체 검사 이력입니다. 결과 페이지에서 점수, 기준점 비교,
                AI 진단을 확인할 수 있습니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href={`/projects/${projectId}/settings`} label="프로젝트 설정" />
              <RefreshButton isLoading={isLoading} onClick={() => void loadCheckRuns()} />
            </div>
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            description="저장된 로그인 세션이 있으면 자동으로 검사 이력을 조회합니다."
            title="로그인 세션 확인 중"
            tone="info"
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            description="프로젝트 ID 또는 현재 사용자 권한을 확인하세요."
            title="검사 이력을 찾을 수 없습니다"
            tone="danger"
          />
        )}

        {result.state === "unavailable" && (
          <Notice
            description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
            title="요청 실패"
            tone="danger"
          />
        )}

        {result.state === "success" && (
          <>
            <SummaryCard lastUpdatedAt={lastUpdatedAt} summary={summary} />
            <ScoreTrendCard checkRuns={checkRuns} />
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-700">
            최근 실행 요약
          </p>
          <h2 className="mt-3 text-2xl font-bold text-slate-900">
            최근 검사 {summary.total}개
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            마지막 조회: {lastUpdatedAt ?? "아직 없음"}
          </p>
        </div>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          로드 {summary.total}개
        </span>
      </div>

      <dl className="mt-6 grid gap-4 md:grid-cols-5">
        <Metric label="전체" value={`${summary.total}개`} />
        <Metric label="진행 중" value={`${summary.active}개`} />
        <Metric label="완료" value={`${summary.completed}개`} />
        <Metric label="실패" value={`${summary.failed}개`} />
        <Metric label="취소" value={`${summary.cancelled}개`} />
      </dl>
    </section>
  );
}

function ScoreTrendCard({ checkRuns }: { checkRuns: CheckRunSummary[] }) {
  const series = buildScoreTrendSeries(checkRuns);
  const runCount = scoredRunCount(series);

  if (runCount < 2) {
    return null;
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-700">점수 추이</p>
      <h2 className="mt-3 text-2xl font-bold text-slate-900">최근 {runCount}회 검사 추이</h2>
      <p className="mt-2 break-keep text-sm text-slate-500">
        항목을 선택해 종합·카테고리별 추이를 볼 수 있습니다. 점 색상은 점수 구간을 나타냅니다 —
        90+ 좋음 · 50–89 보통 · 0–49 개선 필요.
      </p>
      <div className="mt-5">
        <ScoreTrendPanel series={series} />
      </div>
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
  const [expandedStreaks, setExpandedStreaks] = useState<ReadonlySet<string>>(new Set());

  if (checkRuns.length === 0) {
    return (
      <section className="rounded-3xl border border-dashed border-slate-200 bg-white/60 p-6">
        <h2 className="text-xl font-semibold">검사 없음</h2>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          아직 실행된 검사가 없습니다. 대시보드에서 검사를 시작하면 이곳에 이력이
          기록됩니다.
        </p>
      </section>
    );
  }

  const dateGroups = buildDateGroups(checkRuns);

  const toggleStreak = (key: string) => {
    setExpandedStreaks((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 이력</h2>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {checkRuns.length}개
        </span>
      </div>
      <div className="divide-y divide-slate-200 overflow-hidden rounded-2xl border border-slate-200">
        {dateGroups.map((group) => (
          <div key={group.dateLabel}>
            <p className="border-b border-slate-200 bg-slate-50 px-4 py-1.5 text-xs font-semibold text-slate-500">
              {group.dateLabel}
            </p>
            <ul className="divide-y divide-slate-100">
              {group.entries.map((entry) =>
                entry.kind === "run" ? (
                  <CheckRunRow
                    checkRun={entry.checkRun}
                    key={entry.checkRun.id}
                    projectId={projectId}
                  />
                ) : (
                  <CollapsedStreakRows
                    entry={entry}
                    isExpanded={expandedStreaks.has(entry.key)}
                    key={entry.key}
                    onToggle={() => toggleStreak(entry.key)}
                    projectId={projectId}
                  />
                )
              )}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          className="rounded-2xl border border-cyan-300 px-4 py-2 text-sm font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreCheckRuns || isLoadingMore}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMore ? "더 불러오는 중" : "검사 더 보기"}
        </button>
        <p className="text-sm text-slate-500">
          {hasMoreCheckRuns
            ? `${LIST_LIMIT}개 단위로 다음 실행 이력을 불러옵니다.`
            : "현재 로드된 목록이 마지막 페이지입니다."}
        </p>
      </div>

      {listMessage && (
        <p className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-700">
          {listMessage}
        </p>
      )}
    </section>
  );
}

type CheckRunListEntry =
  | { kind: "run"; checkRun: CheckRunSummary }
  | { kind: "collapsed"; key: string; checkRuns: CheckRunSummary[] };

type CheckRunDateGroup = {
  dateLabel: string;
  entries: CheckRunListEntry[];
};

// 하루 안에서 연속된 정기 검사(완료)가 4건 이상이면 앞 2건만 남기고 접는다.
const SCHEDULED_STREAK_VISIBLE = 2;
const SCHEDULED_STREAK_COLLAPSE_MIN = 4;

function isCollapsibleScheduledRun(checkRun: CheckRunSummary): boolean {
  return checkRun.trigger_source === "scheduled" && checkRun.status === "COMPLETED";
}

function collapseScheduledStreaks(
  checkRuns: CheckRunSummary[],
  dateLabel: string
): CheckRunListEntry[] {
  const entries: CheckRunListEntry[] = [];
  let streak: CheckRunSummary[] = [];

  const flushStreak = () => {
    if (streak.length >= SCHEDULED_STREAK_COLLAPSE_MIN) {
      for (const checkRun of streak.slice(0, SCHEDULED_STREAK_VISIBLE)) {
        entries.push({ kind: "run", checkRun });
      }
      const hidden = streak.slice(SCHEDULED_STREAK_VISIBLE);
      entries.push({
        kind: "collapsed",
        key: `${dateLabel}:${hidden[0].id}`,
        checkRuns: hidden
      });
    } else {
      for (const checkRun of streak) {
        entries.push({ kind: "run", checkRun });
      }
    }
    streak = [];
  };

  for (const checkRun of checkRuns) {
    if (isCollapsibleScheduledRun(checkRun)) {
      streak.push(checkRun);
    } else {
      flushStreak();
      entries.push({ kind: "run", checkRun });
    }
  }
  flushStreak();

  return entries;
}

function buildDateGroups(checkRuns: CheckRunSummary[]): CheckRunDateGroup[] {
  const grouped: { dateLabel: string; checkRuns: CheckRunSummary[] }[] = [];

  for (const checkRun of checkRuns) {
    const dateLabel = formatDateWithWeekday(checkRun.queued_at);
    const lastGroup = grouped[grouped.length - 1];

    if (lastGroup && lastGroup.dateLabel === dateLabel) {
      lastGroup.checkRuns.push(checkRun);
    } else {
      grouped.push({ dateLabel, checkRuns: [checkRun] });
    }
  }

  return grouped.map((group) => ({
    dateLabel: group.dateLabel,
    entries: collapseScheduledStreaks(group.checkRuns, group.dateLabel)
  }));
}

function CollapsedStreakRows({
  entry,
  isExpanded,
  onToggle,
  projectId
}: {
  entry: Extract<CheckRunListEntry, { kind: "collapsed" }>;
  isExpanded: boolean;
  onToggle: () => void;
  projectId: string;
}) {
  return (
    <>
      {isExpanded &&
        entry.checkRuns.map((checkRun) => (
          <CheckRunRow checkRun={checkRun} key={checkRun.id} projectId={projectId} />
        ))}
      <li>
        <button
          className="w-full px-4 py-2 text-left text-xs font-bold text-cyan-700 transition hover:bg-cyan-50"
          onClick={onToggle}
          type="button"
        >
          {isExpanded ? "정기 검사 접기" : `같은 정기 검사 ${entry.checkRuns.length}건 더 보기`}
        </button>
      </li>
    </>
  );
}

const ACTIVE_ROW_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);

function getStatusDotClassName(status: CheckRunStatus): string {
  if (status === "COMPLETED") {
    return "bg-emerald-500";
  }

  if (status === "FAILED") {
    return "bg-rose-500";
  }

  if (status === "CANCELLED") {
    return "bg-slate-400";
  }

  return "animate-pulse bg-cyan-500";
}

function getStatusTextClassName(status: CheckRunStatus): string {
  if (status === "COMPLETED") {
    return "text-emerald-700";
  }

  if (status === "FAILED") {
    return "text-rose-700";
  }

  if (status === "CANCELLED") {
    return "text-slate-500";
  }

  return "text-cyan-700";
}

const riskChipClassName: Record<"STABLE" | "WARNING" | "RISK", string> = {
  STABLE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  WARNING: "bg-amber-50 text-amber-700 ring-amber-200",
  RISK: "bg-rose-50 text-rose-700 ring-rose-200"
};

function CheckRunRow({
  checkRun,
  projectId
}: {
  checkRun: CheckRunSummary;
  projectId: string;
}) {
  const score = checkRun.score ?? null;
  const isActive = ACTIVE_ROW_STATUSES.has(checkRun.status);

  return (
    <li>
      <Link
        className="grid grid-cols-[76px_58px_minmax(0,1fr)_auto_14px] items-center gap-3 px-4 py-2.5 transition hover:bg-slate-50 sm:grid-cols-[76px_58px_60px_minmax(0,1fr)_auto_14px]"
        href={`/projects/${projectId}/check-runs/${checkRun.id}`}
      >
        <span
          className={`flex items-center gap-1.5 text-xs font-bold ${getStatusTextClassName(checkRun.status)}`}
        >
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${getStatusDotClassName(checkRun.status)}`}
          />
          {checkRunStatusCopy[checkRun.status]}
        </span>
        <span className="whitespace-nowrap text-sm text-slate-700">
          {formatTimeOfDay(checkRun.queued_at)}
        </span>
        <span className="hidden whitespace-nowrap text-xs text-slate-500 sm:block">
          {isActive ? "진행 중" : formatDuration(checkRun.started_at, checkRun.finished_at)}
        </span>
        <span className="min-w-0">
          {score ? (
            <span
              className={`inline-flex max-w-full items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${riskChipClassName[score.deployment_risk]}`}
            >
              {score.overall_score}점 · {score.grade} ·{" "}
              {deploymentRiskLabel(score.deployment_risk)}
            </span>
          ) : checkRun.failure_reason ? (
            <span className="block truncate text-xs text-rose-700">
              {checkRun.failure_reason}
            </span>
          ) : (
            <span className="text-xs text-slate-400">—</span>
          )}
        </span>
        <span className="flex items-center justify-end gap-1.5">
          <span className="whitespace-nowrap rounded-full border border-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
            {triggerSourceLabel(checkRun.trigger_source)}
          </span>
          {checkRun.deploy_ref && (
            <span className="hidden whitespace-nowrap rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-500 sm:block">
              {checkRun.deploy_ref.slice(0, 7)}
            </span>
          )}
        </span>
        <svg className="h-3.5 w-3.5 text-slate-300" fill="none" viewBox="0 0 16 16">
          <path
            d="M6 4l4 4-4 4"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.5"
          />
        </svg>
      </Link>
    </li>
  );
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

const checkRunListMessageByState: Record<Exclude<CheckRunListResult["state"], "success">, string> =
  {
    unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
    "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요.",
    unavailable: "검사 이력을 더 불러오지 못했습니다. 잠시 후 다시 시도하세요."
  };
