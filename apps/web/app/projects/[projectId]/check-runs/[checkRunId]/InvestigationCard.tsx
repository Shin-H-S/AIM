"use client";

import type { AgentInvestigation } from "@/lib/api";

export type InvestigationCardState =
  | "idle"
  | "loading"
  | "missing"
  | "requested"
  | "unauthorized"
  | "error";

const ROOT_CAUSE_LABELS: Record<string, string> = {
  service_down: "서비스 다운",
  ssl_invalid: "SSL 무효",
  server_slow: "서버 지연",
  frontend_regression: "프런트 성능 회귀",
  ui_regression: "UI 파손",
  scenario_stale: "시나리오 스테일",
  measurement_noise: "측정 노이즈"
};

const BREAKAGE_CAUSES = new Set(["service_down", "ssl_invalid", "ui_regression"]);
const ALL_CLEAR_CAUSES = new Set(["scenario_stale", "measurement_noise"]);

function rootCauseBadgeClassName(rootCause: string): string {
  if (BREAKAGE_CAUSES.has(rootCause)) {
    return "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300";
  }
  if (ALL_CLEAR_CAUSES.has(rootCause)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300";
  }
  return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300";
}

function generatorLabel(generator: string): string {
  if (generator === "rule") {
    return "규칙 판정";
  }
  if (generator.endsWith("-fallback")) {
    return "규칙 폴백";
  }
  if (generator.startsWith("llm:")) {
    return `LLM 판별 (${generator.slice(4)})`;
  }
  return generator;
}

function formatDurationMs(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  return `${(durationMs / 1000).toFixed(1)}초`;
}

export function InvestigationCard({
  investigation,
  state,
  canRequest,
  onRequest
}: {
  investigation: AgentInvestigation | null;
  state: InvestigationCardState;
  canRequest: boolean;
  onRequest: () => void;
}) {
  const totalLlmTokens = investigation
    ? investigation.llm_calls.reduce(
        (sum, call) => sum + call.input_tokens + call.output_tokens,
        0
      )
    : 0;

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-bold text-slate-900 dark:text-white">🕵️ 조사 에이전트</h2>
          {investigation && (
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${rootCauseBadgeClassName(
                investigation.root_cause
              )}`}
            >
              {ROOT_CAUSE_LABELS[investigation.root_cause] ?? investigation.root_cause}
            </span>
          )}
          {investigation && (
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
              신뢰 {investigation.confidence === "high" ? "높음" : "낮음"} ·{" "}
              {generatorLabel(investigation.generator)}
            </span>
          )}
        </div>
        {!investigation && state === "missing" && canRequest && (
          <button
            className="rounded-xl border border-cyan-300 bg-cyan-50 px-3 py-1.5 text-xs font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100 dark:border-cyan-800 dark:bg-cyan-950 dark:text-cyan-400 dark:hover:bg-cyan-900/60"
            onClick={onRequest}
            type="button"
          >
            조사 시작
          </button>
        )}
      </div>

      {investigation ? (
        <>
          <p className="mt-2 break-keep text-sm leading-6 text-slate-700 dark:text-slate-200">
            {investigation.summary}
          </p>
          <p className="mt-1 break-keep text-sm leading-6 text-slate-700 dark:text-slate-200">
            <span className="font-bold text-cyan-700 dark:text-cyan-400">조치 제안</span>{" "}
            {investigation.recommendation}
          </p>
          <details className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
            <summary className="cursor-pointer text-xs font-bold text-slate-600 dark:text-slate-300">
              근거 타임라인 — 도구 호출 {investigation.tool_calls.length}회
            </summary>
            <ol className="mt-2 space-y-1.5">
              {investigation.tool_calls.map((call) => (
                <li className="flex gap-2 text-xs leading-5" key={`${call.step}-${call.tool}`}>
                  <span className="shrink-0 font-mono font-bold text-cyan-700 dark:text-cyan-400">
                    {call.step}
                  </span>
                  <span className="shrink-0 font-mono text-slate-600 dark:text-slate-300">
                    {call.tool}
                  </span>
                  <span className="break-all text-slate-500 dark:text-slate-400">
                    {call.result_summary}
                  </span>
                </li>
              ))}
            </ol>
          </details>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            소요 {formatDurationMs(investigation.duration_ms)} · 재검사{" "}
            {investigation.recheck_used ? "1회 수행" : "미수행"} · 무단 도구 시도{" "}
            {investigation.violations.length}건
            {totalLlmTokens > 0 ? ` · LLM ${totalLlmTokens.toLocaleString()} 토큰` : ""}
          </p>
        </>
      ) : state === "requested" ? (
        <p className="mt-2 text-sm leading-6 text-cyan-700 dark:text-cyan-400">
          조사를 시작했습니다. 재검사가 포함되면 몇 분 걸릴 수 있고, 완료되면 자동으로
          표시됩니다.
        </p>
      ) : state === "loading" ? (
        <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
          조사 결과를 불러오는 중입니다.
        </p>
      ) : state === "unauthorized" ? (
        <p className="mt-2 text-sm font-semibold leading-6 text-rose-600 dark:text-rose-400">
          토큰이 없거나 만료되었거나, 이 조사에 접근할 권한이 없습니다.
        </p>
      ) : state === "error" ? (
        <p className="mt-2 text-sm font-semibold leading-6 text-rose-600 dark:text-rose-400">
          조사 요청이 실패했습니다. API 서버 상태를 확인한 뒤 다시 시도하세요.
        </p>
      ) : (
        <p className="mt-2 break-keep text-sm leading-6 text-slate-500 dark:text-slate-400">
          이 검사에 대한 조사가 아직 없습니다. 인시던트가 열리면 자동으로 시작되고, 종결된
          검사라면 수동으로도 시작할 수 있습니다.
        </p>
      )}
    </article>
  );
}
