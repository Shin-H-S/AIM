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

export function formatTimeOfDay(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", { timeStyle: "short" }).format(new Date(value));
}

export function formatDateWithWeekday(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "full" }).format(new Date(value));
}

// 시작~종료 소요 시간. 아직 끝나지 않았거나 계산할 수 없으면 "—".
export function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt || !finishedAt) {
    return "—";
  }

  const elapsedMs = new Date(finishedAt).getTime() - new Date(startedAt).getTime();

  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    return "—";
  }

  const totalSeconds = Math.round(elapsedMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds}초`;
  }

  return `${minutes}분 ${seconds}초`;
}

export function formatRelativeTime(value: string, now: Date = new Date()): string {
  const elapsedMs = now.getTime() - new Date(value).getTime();

  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    return formatDateTime(value);
  }

  const minutes = Math.floor(elapsedMs / 60_000);

  if (minutes < 1) {
    return "방금 전";
  }

  if (minutes < 60) {
    return `${minutes}분 전`;
  }

  const hours = Math.floor(minutes / 60);

  if (hours < 24) {
    return `${hours}시간 전`;
  }

  const days = Math.floor(hours / 24);

  if (days === 1) {
    return "어제";
  }

  if (days < 7) {
    return `${days}일 전`;
  }

  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(new Date(value));
}
