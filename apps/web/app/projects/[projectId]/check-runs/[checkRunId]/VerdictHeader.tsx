"use client";

import type { AgentInvestigation, CheckRunStatus, ScoreResult } from "@/lib/api";

/**
 * 판정 헤더 — 이 화면이 답해야 할 단 하나의 질문에 첫 블록이 답한다(R1).
 *
 * 문구는 판단 보조형이다(D3): "배포해도 됩니다"라고 단정하지 않고
 * "막을 이슈가 없습니다"까지만 말한다 — 배포 결정과 책임은 사용자의 것이다.
 * 결론은 이미 계산된 결정론 값(deployment_risk·gate_reason)에서 도출하고,
 * 에이전트 조사 결론이 있으면 원인·조치를 같은 블록에 병합한다(R4).
 */

const ROOT_CAUSE_LABELS: Record<string, string> = {
  service_down: "서비스 다운",
  ssl_invalid: "SSL 무효",
  server_slow: "서버 지연",
  frontend_regression: "프런트 성능 회귀",
  ui_regression: "UI 파손",
  scenario_stale: "시나리오 스테일",
  measurement_noise: "측정 노이즈"
};

const ACTIVE_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);

type Tone = "good" | "warn" | "bad" | "info";

const TONE_CLASSES: Record<Tone, { stripe: string; badge: string }> = {
  good: {
    stripe: "border-l-emerald-500",
    badge:
      "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-900"
  },
  warn: {
    stripe: "border-l-amber-500",
    badge:
      "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-900"
  },
  bad: {
    stripe: "border-l-rose-500",
    badge:
      "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:ring-rose-900"
  },
  info: {
    stripe: "border-l-cyan-500",
    badge:
      "bg-cyan-50 text-cyan-800 ring-cyan-200 dark:bg-cyan-950 dark:text-cyan-300 dark:ring-cyan-900"
  }
};

function deriveVerdict(
  status: CheckRunStatus,
  score: ScoreResult | null,
  failureReason: string | null
): { tone: Tone; badge: string; sentence: string; reason: string | null } {
  if (ACTIVE_STATUSES.has(status)) {
    return {
      tone: "info",
      badge: "진행 중",
      sentence: "검사가 아직 진행 중입니다.",
      reason: "판정은 검사가 끝나면 이 자리에 표시됩니다."
    };
  }

  if (status === "CANCELLED") {
    return {
      tone: "info",
      badge: "취소됨",
      sentence: "취소된 검사입니다.",
      reason: null
    };
  }

  if (score === null) {
    return {
      tone: "bad",
      badge: "판정 불가",
      sentence: "검사가 완료되지 못해 판정할 수 없습니다.",
      reason: failureReason
    };
  }

  if (score.deployment_risk === "STABLE") {
    return {
      tone: "good",
      badge: "안정",
      sentence: "이번 배포를 막을 이슈가 없습니다.",
      reason: null
    };
  }

  if (score.deployment_risk === "WARNING") {
    return {
      tone: "warn",
      badge: "주의",
      sentence: "배포를 막지는 않지만 주의할 변화가 있습니다.",
      reason: score.gate_reason ?? failureReason
    };
  }

  return {
    tone: "bad",
    badge: "위험",
    sentence: "조치가 필요한 이슈가 있습니다.",
    reason: score.gate_reason ?? failureReason
  };
}

export function VerdictHeader({
  failureReason,
  investigation,
  score,
  status
}: {
  failureReason: string | null;
  investigation: AgentInvestigation | null;
  score: ScoreResult | null;
  status: CheckRunStatus;
}) {
  const verdict = deriveVerdict(status, score, failureReason);
  const tone = TONE_CLASSES[verdict.tone];

  return (
    <section
      aria-label="검사 판정"
      className={`rounded-2xl border border-l-4 border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900 ${tone.stripe}`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${tone.badge}`}
        >
          {verdict.badge}
        </span>
        <h2 className="text-lg font-extrabold tracking-tight text-slate-900 dark:text-white">
          {verdict.sentence}
        </h2>
        {score && (
          <span className="font-mono text-sm font-bold tabular-nums text-slate-500 dark:text-slate-400">
            {score.overall_score}점 · {score.grade}
          </span>
        )}
      </div>

      {verdict.reason && (
        <p className="mt-1.5 break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
          {verdict.reason}
        </p>
      )}

      {investigation && (
        <p className="mt-2 border-t border-slate-100 pt-2 text-sm leading-6 text-slate-700 dark:border-slate-800 dark:text-slate-200">
          <span className="font-bold">
            🕵️ 조사 결론: {ROOT_CAUSE_LABELS[investigation.root_cause] ?? investigation.root_cause}
          </span>
          <span className="text-slate-400 dark:text-slate-500">
            {" "}
            · 신뢰 {investigation.confidence === "high" ? "높음" : "낮음"}
          </span>
          {" — "}
          {investigation.recommendation}{" "}
          <a
            className="font-semibold text-cyan-700 underline underline-offset-2 dark:text-cyan-400"
            href="#investigation"
          >
            근거 보기
          </a>
        </p>
      )}
    </section>
  );
}
