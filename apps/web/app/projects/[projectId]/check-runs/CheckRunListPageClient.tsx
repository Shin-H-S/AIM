"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchCheckRuns,
  type CheckRunListResult,
  type CheckRunSummary
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import { formatDateTime, formatNullableDateTime } from "@/lib/format";
import { ScoreTrendPanel, type ScoreTrendSeries } from "@/components/charts";
import {
  Badge,
  CheckRunStatusBadge,
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
      setListMessage("더 불러올 CheckRun이 없습니다.");
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
                AIM Check Runs
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                CheckRun 이력
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                이 프로젝트의 전체 검사 이력입니다. 결과 페이지에서 점수, baseline 비교,
                AI 진단을 확인할 수 있습니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href={`/projects/${projectId}/settings`} label="Project 설정" />
              <RefreshButton isLoading={isLoading} onClick={() => void loadCheckRuns()} />
            </div>
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            description="저장된 로그인 세션이 있으면 자동으로 CheckRun 이력을 조회합니다."
            title="로그인 세션 확인 중"
            tone="info"
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            description="Project ID 또는 현재 사용자 권한을 확인하세요."
            title="CheckRun 이력을 찾을 수 없습니다"
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
            최근 CheckRun {summary.total}개
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
        <Metric label="Total" value={`${summary.total}개`} />
        <Metric label="Active" value={`${summary.active}개`} />
        <Metric label="Completed" value={`${summary.completed}개`} />
        <Metric label="Failed" value={`${summary.failed}개`} />
        <Metric label="Cancelled" value={`${summary.cancelled}개`} />
      </dl>
    </section>
  );
}

function formatTrendLabel(value: string): string {
  const date = new Date(value);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${date.getMonth() + 1}/${date.getDate()} ${hours}:${minutes}`;
}

const trendSeriesDefs: {
  key: string;
  label: string;
  pick: (score: NonNullable<CheckRunSummary["score"]>) => number | null | undefined;
}[] = [
  { key: "overall", label: "종합", pick: (score) => score.overall_score },
  { key: "availability", label: "가용성", pick: (score) => score.availability_score },
  {
    key: "functional_stability",
    label: "기능 안정성",
    pick: (score) => score.functional_stability_score
  },
  { key: "web_performance", label: "웹 성능", pick: (score) => score.web_performance_score },
  { key: "accessibility", label: "접근성", pick: (score) => score.accessibility_score },
  {
    key: "seo_basic_quality",
    label: "SEO/기본 품질",
    pick: (score) => score.seo_basic_quality_score
  }
];

function ScoreTrendCard({ checkRuns }: { checkRuns: CheckRunSummary[] }) {
  const oldestFirst = [...checkRuns].reverse();
  const series: ScoreTrendSeries[] = trendSeriesDefs.map((def) => ({
    key: def.key,
    label: def.label,
    points: oldestFirst.flatMap((checkRun) => {
      const value = checkRun.score ? def.pick(checkRun.score) : null;
      return value === null || value === undefined
        ? []
        : [{ label: formatTrendLabel(checkRun.queued_at), score: value }];
    })
  }));
  const scoredRunCount = series[0].points.length;

  if (scoredRunCount < 2) {
    return null;
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-700">점수 추이</p>
      <h2 className="mt-3 text-2xl font-bold text-slate-900">
        최근 {scoredRunCount}회 검사 추이
      </h2>
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
  if (checkRuns.length === 0) {
    return (
      <section className="rounded-3xl border border-dashed border-slate-200 bg-white/60 p-6">
        <h2 className="text-xl font-semibold">CheckRun 없음</h2>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          아직 실행된 CheckRun이 없습니다. Dashboard에서 검사를 시작하면 이곳에 이력이
          기록됩니다.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 이력</h2>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
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
          className="rounded-2xl border border-cyan-300 px-4 py-2 text-sm font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreCheckRuns || isLoadingMore}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMore ? "더 불러오는 중" : "CheckRun 더 보기"}
        </button>
        <p className="text-sm text-slate-500">
          {hasMoreCheckRuns
            ? `${LIST_LIMIT}개 단위로 다음 실행 이력을 불러옵니다.`
            : "현재 로드된 목록이 마지막 page입니다."}
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

function CheckRunCard({
  checkRun,
  projectId
}: {
  checkRun: CheckRunSummary;
  projectId: string;
}) {
  return (
    <li className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          <CheckRunStatusBadge status={checkRun.status} />
          <Badge label={checkRun.trigger_source} />
        </div>
        <LinkButton
          href={`/projects/${projectId}/check-runs/${checkRun.id}`}
          label="결과 보기"
          variant="dark"
        />
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-3">
        <Metric label="Queued" value={formatDateTime(checkRun.queued_at)} />
        <Metric label="Started" value={formatNullableDateTime(checkRun.started_at)} />
        <Metric label="Finished" value={formatNullableDateTime(checkRun.finished_at)} />
      </dl>

      {checkRun.failure_reason && (
        <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {checkRun.failure_reason}
        </p>
      )}
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
    "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
    unavailable: "CheckRun 이력을 더 불러오지 못했습니다. 잠시 후 다시 시도하세요."
  };
