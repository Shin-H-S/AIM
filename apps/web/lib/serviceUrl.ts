// 붙여넣기로 흔히 섞여 들어오는, 화면에 보이지 않는 문자들. trim()은 이들을 지우지
// 못해 new URL() 파싱이 조용히 실패한다. 소스에서 읽히도록 이스케이프로만 적는다.
// 제로폭(200B~200D) · 방향 표시(200E/200F) · word joiner(2060) · BOM(FEFF) · soft hyphen(00AD)
const INVISIBLE_CHARACTERS = /[\u200B-\u200F\u2060\uFEFF\u00AD]/g;

const HAS_SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//;

/** 사람이 입력한 주소를 파싱 가능한 형태로 다듬는다 — 스킴 생략은 https로 본다. */
export function normalizeServiceUrl(value: string): string {
  const cleaned = value.replace(INVISIBLE_CHARACTERS, "").trim();
  if (!cleaned || HAS_SCHEME.test(cleaned)) {
    return cleaned;
  }
  // "example.com/path"처럼 스킴만 빠진 입력은 거부 대신 https로 보정한다.
  // 반대로 "mailto:..."처럼 콜론이 있는 입력은 그대로 둬서 아래 검증이 걸러내게 한다.
  return cleaned.includes(":") ? cleaned : `https://${cleaned}`;
}

export function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
