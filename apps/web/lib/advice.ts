import type { AvailabilityResult, SslResult } from "./api";
import { formatMilliseconds } from "./format";

export const SSL_EXPIRY_ADVICE_THRESHOLD_DAYS = 30;
export const REDIRECT_CHAIN_ADVICE_THRESHOLD = 2;

export function buildAvailabilityAdvice(
  result: AvailabilityResult,
  responseTimeThresholdMs: number | null
): string[] {
  const advice: string[] = [];

  if (!result.is_available) {
    advice.push(
      "서비스가 정상 응답하지 않습니다. 최근 배포의 롤백 필요 여부, 서버·컨테이너 상태, 외부 의존성 장애를 순서대로 확인하세요."
    );
  }

  if (result.timed_out) {
    advice.push(
      "요청이 제한 시간 안에 완료되지 않았습니다. 서버 부하, 느린 업스트림 호출(DB·외부 API), 네트워크 경로를 점검하세요."
    );
  }

  if (
    result.response_time_ms !== null &&
    responseTimeThresholdMs !== null &&
    result.response_time_ms > responseTimeThresholdMs
  ) {
    advice.push(
      `응답 시간(${formatMilliseconds(result.response_time_ms)})이 프로젝트 임계값(${formatMilliseconds(
        responseTimeThresholdMs
      )})을 초과했습니다. 서버 처리 시간(TTFB)과 DB 쿼리를 먼저 점검하고, CDN·응답 캐시 적용을 검토하세요.`
    );
  }

  if (result.redirect_count >= REDIRECT_CHAIN_ADVICE_THRESHOLD) {
    advice.push(
      `리다이렉트가 ${result.redirect_count}회 연쇄되고 있습니다. http→https, www 통일, 후행 슬래시 같은 중복 리다이렉트를 정리해 첫 요청이 최종 URL로 한 번에 연결되게 하세요.`
    );
  }

  if (!result.uses_https) {
    advice.push(
      "HTTP로 서비스되고 있습니다. TLS 인증서를 적용하고 모든 HTTP 요청을 HTTPS로 리다이렉트하세요."
    );
  }

  return advice;
}

export function buildSslAdvice(result: SslResult): string[] {
  if (!result.is_applicable) {
    return [];
  }

  if (result.is_valid === false) {
    return [
      "인증서가 유효하지 않습니다. 도메인 일치 여부, 중간 체인 누락, 만료 여부를 확인하고 인증서를 재발급·재배포하세요."
    ];
  }

  if (
    result.days_until_expiration !== null &&
    result.days_until_expiration >= 0 &&
    result.days_until_expiration <= SSL_EXPIRY_ADVICE_THRESHOLD_DAYS
  ) {
    return [
      `인증서가 ${result.days_until_expiration}일 후 만료됩니다. 자동 갱신(certbot, 관리형 인증서 등)을 설정하거나 갱신 일정을 지금 준비하세요.`
    ];
  }

  return [];
}
