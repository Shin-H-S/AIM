import { type AIReportChange, type AIReportDetail, type AIReportIssue } from "@/lib/api";
import { formatDetailDateTime } from "@/lib/format";
import { Metric } from "@/components/ui";

const statementTypeLabels: Record<AIReportIssue["statement_type"], string> = {
  confirmed_observation: "확인된 관찰",
  evidence_based_inference: "근거 기반 추론",
  unknown_cause: "원인 미확인"
};

const severityLabels: Record<AIReportIssue["severity"], string> = {
  info: "정보",
  warning: "주의",
  risk: "위험"
};

export function AIReportDetailPanel({ report }: { report: AIReportDetail }) {
  const payload = report.report_json;

  return (
    <section className="mt-6 grid gap-5">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <h3 className="text-lg font-semibold text-slate-900">상세 리포트 메타데이터</h3>
        <dl className="mt-4 grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
          <Metric label="Report schema" value={report.schema_version} />
          <Metric label="Input schema" value={report.input_schema_version} />
          <Metric label="Generated" value={formatDetailDateTime(payload.generated_at)} />
          <Metric label="Score evidence" value={formatEvidenceIds(payload.score.evidence_ids)} />
          <Metric label="Project ID" value={payload.project_id} />
          <Metric label="CheckRun ID" value={payload.check_run_id} />
        </dl>
      </div>

      <AIReportIssuesList issues={payload.top_issues} />

      <section className="grid gap-4 lg:grid-cols-2">
        <AIReportChangesCard
          changes={payload.improved_areas}
          emptyDescription="이번 리포트에 기록된 개선 영역이 없습니다."
          title="개선된 영역"
        />
        <AIReportChangesCard
          changes={payload.regressed_areas}
          emptyDescription="이번 리포트에 기록된 회귀 영역이 없습니다."
          title="회귀한 영역"
        />
      </section>

      <AIReportWarningsCard warnings={payload.generation_warnings} />
    </section>
  );
}

function AIReportIssuesList({ issues }: { issues: AIReportIssue[] }) {
  if (issues.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">
        <h3 className="text-lg font-semibold">우선 이슈 없음</h3>
        <p className="mt-2 text-sm opacity-80">
          AIReport에 top issue가 없습니다. 안정 상태 리포트일 때 정상적으로 발생할 수 있습니다.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">우선 확인 이슈</h3>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {issues.length}개
        </span>
      </div>
      <ul className="grid gap-4">
        {issues.map((issue) => (
          <li className="rounded-2xl border border-slate-200 bg-slate-50 p-4" key={issue.id}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-900">
                #{issue.priority}
              </span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getSeverityBadgeClassName(
                  issue.severity
                )}`}
              >
                {severityLabels[issue.severity]}
              </span>
              <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
                {statementTypeLabels[issue.statement_type]}
              </span>
              <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
                {issue.category}
              </span>
            </div>

            <h4 className="mt-4 text-lg font-semibold text-slate-900">{issue.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-600">{issue.summary}</p>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Expected user impact
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {issue.expected_user_impact}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Recommended next action
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {issue.recommended_next_action}
                </p>
              </div>
            </div>

            {issue.unknown_reason && (
              <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                원인 미확인 이유: {issue.unknown_reason}
              </p>
            )}

            <div className="mt-4">
              <EvidenceIdList ids={issue.evidence_ids} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AIReportChangesCard({
  changes,
  emptyDescription,
  title
}: {
  changes: AIReportChange[];
  emptyDescription: string;
  title: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
          {changes.length}개
        </span>
      </div>

      {changes.length === 0 ? (
        <p className="text-sm text-slate-500">{emptyDescription}</p>
      ) : (
        <ul className="grid gap-3">
          {changes.map((change) => (
            <li className="rounded-2xl border border-slate-200 bg-slate-50 p-4" key={change.id}>
              <p className="text-sm font-semibold text-slate-900">{change.summary}</p>
              <dl className="mt-3 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                <Metric label="Metric" value={change.metric_name ?? "알 수 없음"} />
                <Metric label="Category" value={change.category} />
                <Metric label="Previous" value={formatReportValue(change.previous_value)} />
                <Metric label="Current" value={formatReportValue(change.current_value)} />
                <Metric label="Delta" value={formatReportValue(change.delta)} />
                <Metric label="Evidence" value={formatEvidenceIds(change.evidence_ids)} />
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AIReportWarningsCard({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <h3 className="text-lg font-semibold text-slate-900">생성 경고</h3>
        <p className="mt-2 text-sm text-slate-500">기록된 generation warning이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-800">
      <h3 className="text-lg font-semibold">생성 경고</h3>
      <ul className="mt-3 grid gap-2 text-sm">
        {warnings.map((warning) => (
          <li className="rounded-xl bg-amber-100 p-3" key={warning}>
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceIdList({ ids }: { ids: string[] }) {
  if (ids.length === 0) {
    return <p className="text-xs text-slate-400">Evidence ID 없음</p>;
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
        Evidence IDs
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {ids.map((id) => (
          <span
            className="rounded-full bg-slate-200 px-2.5 py-1 font-mono text-xs text-slate-600 ring-1 ring-slate-200"
            key={id}
          >
            {id}
          </span>
        ))}
      </div>
    </div>
  );
}

function getSeverityBadgeClassName(severity: AIReportIssue["severity"]) {
  if (severity === "risk") {
    return "bg-rose-50 text-rose-700 ring-rose-200";
  }

  if (severity === "warning") {
    return "bg-amber-50 text-amber-700 ring-amber-200";
  }

  return "bg-cyan-50 text-cyan-700 ring-cyan-200";
}

function formatEvidenceIds(ids: string[]) {
  return ids.length === 0 ? "없음" : ids.join(", ");
}

function formatReportValue(value: string | number | boolean | null) {
  if (value === null) {
    return "없음";
  }

  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return String(value);
}
