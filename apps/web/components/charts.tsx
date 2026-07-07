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
