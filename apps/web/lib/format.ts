export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "아직 없음";
}

export function formatMilliseconds(value: number | null): string {
  return value === null ? "알 수 없음" : `${value}ms`;
}

// Detail/polling screens show seconds so consecutive refreshes are distinguishable.
export function formatDetailDateTime(value: string | null): string {
  if (!value) {
    return "없음";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(new Date(value));
}
