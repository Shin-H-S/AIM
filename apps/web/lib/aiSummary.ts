/**
 * AI 진단 요약의 3단 서식(결론/원인/조치) 파서.
 *
 * 서버의 build_report_summary와 LLM 프롬프트가 이 서식을 계약한다.
 * 계약을 지키지 않은 요약(구서식 리포트, LLM의 서식 이탈)은 null을 돌려주고
 * 호출부가 산문으로 폴백 렌더링한다 — 구조는 보너스이고 내용 유실은 없다.
 */

export type StructuredAISummary = {
  verdict: string;
  cause: string;
  action: string;
};

const SECTION_LABELS = ["결론", "원인", "조치"] as const;

export function parseStructuredSummary(summary: string): StructuredAISummary | null {
  const lines = summary
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length !== SECTION_LABELS.length) {
    return null;
  }

  const values: string[] = [];
  for (const [index, label] of SECTION_LABELS.entries()) {
    const prefix = `${label}:`;
    if (!lines[index].startsWith(prefix)) {
      return null;
    }
    const value = lines[index].slice(prefix.length).trim();
    if (!value) {
      return null;
    }
    values.push(value);
  }

  return { verdict: values[0], cause: values[1], action: values[2] };
}
