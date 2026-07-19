import { useId } from "react";

// AIM 브랜드 심볼 "펄스 타겟" (2026-07-18 확정, 시안 v4).
// 과녁 링(조준·브랜드 시안색) + 십자선(조준선) + 심박 파형(가동 중인 서비스).
// 펄스의 기준선이 좌우 십자선 스텁과 한 줄로 이어지는 것이 형태의 핵심.
// variant:
//  - "full": 십자선 포함. 헤더 등 20px 이상 지면용.
//  - "compact": 십자선 생략 + 파형 진폭·두께 확대. 파비콘급 소형용.
export function AimMark({
  className,
  variant = "full"
}: {
  className?: string;
  variant?: "full" | "compact";
}) {
  const clipId = useId();
  const isFull = variant === "full";

  return (
    <svg aria-hidden className={className} fill="none" viewBox="0 0 48 48">
      <circle
        className="stroke-cyan-600 dark:stroke-cyan-400"
        cx="24"
        cy="24"
        r="16"
        strokeWidth={isFull ? 3.5 : 5}
      />
      {isFull && (
        <g
          className="stroke-slate-900 dark:stroke-slate-100"
          strokeLinecap="round"
          strokeWidth="3.5"
        >
          <line x1="24" x2="24" y1="2.5" y2="8" />
          <line x1="24" x2="24" y1="40" y2="45.5" />
          <line x1="2.5" x2="8" y1="24" y2="24" />
          <line x1="40" x2="45.5" y1="24" y2="24" />
        </g>
      )}
      <clipPath id={clipId}>
        <circle cx="24" cy="24" r={isFull ? 14 : 13} />
      </clipPath>
      <g clipPath={`url(#${clipId})`}>
        <polyline
          className="stroke-slate-900 dark:stroke-slate-100"
          points={
            isFull ? "8,24 17,24 21,14 27,33 31,24 40,24" : "5,24 15,24 21,11 28,36 33,24 43,24"
          }
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={isFull ? 4 : 7}
        />
      </g>
    </svg>
  );
}
