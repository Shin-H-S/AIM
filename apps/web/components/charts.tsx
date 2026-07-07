"use client";

import { useState } from "react";
import { InfoHint } from "./ui";

export type ScoreBand = "good" | "mid" | "bad" | "none";

export function scoreBand(score: number | null): ScoreBand {
  if (score === null) {
    return "none";
  }

  if (score >= 90) {
    return "good";
  }

  if (score >= 50) {
    return "mid";
  }

  return "bad";
}

const bandRingClassName: Record<ScoreBand, string> = {
  good: "text-emerald-500",
  mid: "text-amber-500",
  bad: "text-rose-500",
  none: "text-slate-300"
};

const bandTextClassName: Record<ScoreBand, string> = {
  good: "text-emerald-600",
  mid: "text-amber-600",
  bad: "text-rose-600",
  none: "text-slate-400"
};

const bandBarClassName: Record<ScoreBand, string> = {
  good: "bg-emerald-500",
  mid: "bg-amber-500",
  bad: "bg-rose-500",
  none: "bg-slate-300"
};

export function scoreBarClassName(score: number | null): string {
  return bandBarClassName[scoreBand(score)];
}

const riskDonutClassName: Record<"STABLE" | "WARNING" | "RISK", string> = {
  STABLE: "text-emerald-500",
  WARNING: "text-amber-500",
  RISK: "text-rose-500"
};

export function ScoreDonut({
  grade,
  risk,
  score
}: {
  grade: string;
  risk: "STABLE" | "WARNING" | "RISK";
  score: number;
}) {
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.min(Math.max(score, 0), 100) / 100) * circumference;

  return (
    <div className="relative h-36 w-36">
      <svg className="h-full w-full -rotate-90" viewBox="0 0 144 144">
        <circle
          className="text-slate-200"
          cx="72"
          cy="72"
          fill="none"
          r={radius}
          stroke="currentColor"
          strokeWidth="12"
        />
        {score > 0 && (
          <circle
            className={riskDonutClassName[risk]}
            cx="72"
            cy="72"
            fill="none"
            r={radius}
            stroke="currentColor"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
            strokeWidth="12"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-black tracking-tight text-slate-900">{grade}</span>
        <span className="text-xs font-semibold text-slate-500">{score}/100</span>
      </div>
    </div>
  );
}

export function MiniDonut({
  grade,
  risk,
  score
}: {
  grade: string;
  risk: "STABLE" | "WARNING" | "RISK";
  score: number;
}) {
  const radius = 19;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.min(Math.max(score, 0), 100) / 100) * circumference;

  return (
    <div className="relative h-12 w-12" title={`종합 ${score}/100`}>
      <svg className="h-full w-full -rotate-90" viewBox="0 0 48 48">
        <circle
          className="text-slate-200"
          cx="24"
          cy="24"
          fill="none"
          r={radius}
          stroke="currentColor"
          strokeWidth="5"
        />
        {score > 0 && (
          <circle
            className={riskDonutClassName[risk]}
            cx="24"
            cy="24"
            fill="none"
            r={radius}
            stroke="currentColor"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
            strokeWidth="5"
          />
        )}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-black text-slate-900">
        {grade}
      </span>
    </div>
  );
}

export type ScoreTrendPoint = {
  label: string;
  score: number;
};

const TREND_VIEW = {
  width: 600,
  height: 190,
  left: 34,
  right: 588,
  top: 14,
  bottom: 156
} as const;

function trendX(index: number, count: number): number {
  if (count <= 1) {
    return (TREND_VIEW.left + TREND_VIEW.right) / 2;
  }

  return TREND_VIEW.left + (index / (count - 1)) * (TREND_VIEW.right - TREND_VIEW.left);
}

function trendY(score: number): number {
  const clamped = Math.min(Math.max(score, 0), 100);
  return TREND_VIEW.top + ((100 - clamped) / 100) * (TREND_VIEW.bottom - TREND_VIEW.top);
}

export type ScoreTrendSeries = {
  key: string;
  label: string;
  points: ScoreTrendPoint[];
};

// 시리즈(종합·카테고리) 중 하나를 골라 보는 추이 패널. 점이 2개 미만인 시리즈는 숨긴다.
export function ScoreTrendPanel({ series }: { series: ScoreTrendSeries[] }) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const drawableSeries = series.filter((entry) => entry.points.length >= 2);

  if (drawableSeries.length === 0) {
    return null;
  }

  const activeSeries =
    drawableSeries.find((entry) => entry.key === activeKey) ?? drawableSeries[0];

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {drawableSeries.map((entry) => (
          <button
            className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${
              entry.key === activeSeries.key
                ? "bg-cyan-600 text-white"
                : "border border-slate-200 text-slate-600 hover:border-cyan-400 hover:text-cyan-700"
            }`}
            key={entry.key}
            onClick={() => setActiveKey(entry.key)}
            type="button"
          >
            {entry.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        <ScoreTrendChart points={activeSeries.points} />
      </div>
    </div>
  );
}

// 최근 검사들의 종합 점수 추이. points는 오래된 것부터 순서대로 넘긴다.
export function ScoreTrendChart({ points }: { points: ScoreTrendPoint[] }) {
  const gridScores = [100, 90, 50, 0];
  const linePoints = points
    .map((point, index) => `${trendX(index, points.length)},${trendY(point.score)}`)
    .join(" ");

  return (
    <svg className="h-auto w-full" role="img" viewBox={`0 0 ${TREND_VIEW.width} ${TREND_VIEW.height}`}>
      {gridScores.map((score) => (
        <g key={score}>
          <line
            className="text-slate-200"
            stroke="currentColor"
            strokeDasharray={score === 0 || score === 100 ? undefined : "4 4"}
            x1={TREND_VIEW.left}
            x2={TREND_VIEW.right}
            y1={trendY(score)}
            y2={trendY(score)}
          />
          <text
            className="fill-slate-400 text-[10px] font-semibold"
            textAnchor="end"
            x={TREND_VIEW.left - 6}
            y={trendY(score) + 3}
          >
            {score}
          </text>
        </g>
      ))}
      {points.length > 1 && (
        <polyline
          className="text-cyan-600"
          fill="none"
          points={linePoints}
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2.5"
        />
      )}
      {points.map((point, index) => (
        <circle
          className={bandTextClassName[scoreBand(point.score)]}
          cx={trendX(index, points.length)}
          cy={trendY(point.score)}
          fill="currentColor"
          key={`${point.label}-${index}`}
          r="4.5"
          stroke="white"
          strokeWidth="1.5"
        >
          <title>{`${point.label} · ${point.score}점`}</title>
        </circle>
      ))}
      {points.length > 0 && (
        <>
          <text
            className="fill-slate-400 text-[10px] font-semibold"
            textAnchor="start"
            x={TREND_VIEW.left}
            y={TREND_VIEW.height - 8}
          >
            {points[0].label}
          </text>
          {points.length > 1 && (
            <text
              className="fill-slate-400 text-[10px] font-semibold"
              textAnchor="end"
              x={TREND_VIEW.right}
              y={TREND_VIEW.height - 8}
            >
              {points[points.length - 1].label}
            </text>
          )}
        </>
      )}
    </svg>
  );
}

export function RingGauge({
  hint,
  label,
  score
}: {
  hint?: string;
  label: string;
  score: number | null;
}) {
  const band = scoreBand(score);
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const filled =
    score === null ? 0 : (Math.min(Math.max(score, 0), 100) / 100) * circumference;

  return (
    <div className="flex w-20 flex-col items-center">
      <div className="relative h-16 w-16">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 64 64">
          <circle
            className="text-slate-200"
            cx="32"
            cy="32"
            fill="none"
            r={radius}
            stroke="currentColor"
            strokeWidth="6"
          />
          {score !== null && score > 0 && (
            <circle
              className={bandRingClassName[band]}
              cx="32"
              cy="32"
              fill="none"
              r={radius}
              stroke="currentColor"
              strokeDasharray={`${filled} ${circumference}`}
              strokeLinecap="round"
              strokeWidth="6"
            />
          )}
        </svg>
        <span
          className={`absolute inset-0 flex items-center justify-center text-sm font-bold ${bandTextClassName[band]}`}
        >
          {score === null ? "–" : Math.round(score)}
        </span>
      </div>
      <p className="mt-1.5 break-keep text-center text-[11px] font-semibold leading-4 text-slate-500">
        {label}
        {hint && <InfoHint text={hint} />}
      </p>
    </div>
  );
}

export function ScoreBandLegend({ showExcluded = false }: { showExcluded?: boolean }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold text-slate-400">
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        90–100 좋음
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-amber-500" />
        50–89 보통
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-rose-500" />
        0–49 개선 필요
      </span>
      {showExcluded && (
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-slate-300" />– 평가 제외
        </span>
      )}
    </div>
  );
}

export function ThresholdBar({
  goodLabel,
  goodTo,
  hint,
  label,
  max,
  midLabel,
  midTo,
  value,
  valueLabel
}: {
  goodLabel: string;
  goodTo: number;
  hint?: string;
  label: string;
  max: number;
  midLabel: string;
  midTo: number;
  value: number | null;
  valueLabel: string;
}) {
  const band: ScoreBand =
    value === null ? "none" : value <= goodTo ? "good" : value <= midTo ? "mid" : "bad";
  const markerLeft = value === null ? 0 : Math.min(Math.max((value / max) * 100, 1), 99);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          {label}
          {hint && <InfoHint text={hint} />}
        </p>
        <p className={`text-sm font-bold ${bandTextClassName[band]}`}>{valueLabel}</p>
      </div>
      <div className="relative mt-2">
        <div className="flex h-2 overflow-hidden rounded-full">
          <div className="h-full bg-emerald-200" style={{ width: `${(goodTo / max) * 100}%` }} />
          <div
            className="h-full bg-amber-200"
            style={{ width: `${((midTo - goodTo) / max) * 100}%` }}
          />
          <div className="h-full flex-1 bg-rose-200" />
        </div>
        {value !== null && (
          <span
            className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded-full bg-slate-800"
            style={{ left: `${markerLeft}%` }}
          />
        )}
      </div>
      <div className="relative mt-1 h-4 text-[10px] font-semibold text-slate-400">
        <span
          className="absolute -translate-x-1/2 whitespace-nowrap"
          style={{ left: `${(goodTo / max) * 100}%` }}
        >
          {goodLabel}
        </span>
        <span
          className="absolute -translate-x-1/2 whitespace-nowrap"
          style={{ left: `${(midTo / max) * 100}%` }}
        >
          {midLabel}
        </span>
      </div>
    </div>
  );
}
