// AIM 브랜드 심볼 "록온(Lock-on)" — 과녁 링 + 십자선 + 중심점.
// 워드마크 "AIM."의 시안색 마침표를 과녁의 중심점으로 승격한 마크로,
// 16px 이하로 쓸 때는 withTicks를 끄고 링+점만 남겨 판독성을 지킨다.
export function AimMark({
  className,
  withTicks = true
}: {
  className?: string;
  withTicks?: boolean;
}) {
  return (
    <svg aria-hidden className={className} fill="none" viewBox="0 0 48 48">
      <circle cx="24" cy="24" r="15.5" stroke="#0891b2" strokeWidth="4" />
      {withTicks && (
        <>
          <line stroke="#0f172a" strokeLinecap="round" strokeWidth="4" x1="24" x2="24" y1="2.5" y2="9" />
          <line stroke="#0f172a" strokeLinecap="round" strokeWidth="4" x1="24" x2="24" y1="39" y2="45.5" />
          <line stroke="#0f172a" strokeLinecap="round" strokeWidth="4" x1="2.5" x2="9" y1="24" y2="24" />
          <line stroke="#0f172a" strokeLinecap="round" strokeWidth="4" x1="39" x2="45.5" y1="24" y2="24" />
        </>
      )}
      <circle cx="24" cy="24" fill="#0891b2" r="6" />
    </svg>
  );
}
