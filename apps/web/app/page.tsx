"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getStoredAccessToken } from "@/lib/auth";

// 마케팅 홈. 로그인 폼은 /login 으로 분리되었고(2026-07-18 리디자인),
// 이 페이지의 역할은 "무엇을 얻는지(히어로 리포트)"와 "무엇을 하면 되는지(4단계 흐름)"를
// 처음 온 사용자에게 3초 안에 보여주는 것이다.
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (getStoredAccessToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  return (
    <main className="bg-[#f4f9fb] dark:bg-slate-950">
      <Hero />
      <FlowSection />
      <FeatureSection />
      <CtaBand />
      <footer className="mx-auto flex w-full max-w-6xl flex-wrap justify-between gap-4 px-6 pb-12 pt-9 text-sm text-slate-500 dark:text-slate-400">
        <span>AIM — AI Quality Monitor</span>
        <a
          className="transition hover:text-cyan-700"
          href="https://github.com/Shin-H-S/AIM"
          rel="noreferrer"
          target="_blank"
        >
          GitHub에서 소스 보기
        </a>
      </footer>
    </main>
  );
}

function Hero() {
  return (
    <header className="relative overflow-hidden">
      {/* 모눈 배경: 모니터링 좌표계 모티프 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-35 [mask-image:radial-gradient(ellipse_90%_70%_at_50%_0%,#000_30%,transparent_75%)] dark:hidden"
        style={{
          backgroundImage:
            "linear-gradient(#d9e6ec 1px, transparent 1px), linear-gradient(90deg, #d9e6ec 1px, transparent 1px)",
          backgroundSize: "48px 48px"
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 hidden opacity-40 [mask-image:radial-gradient(ellipse_90%_70%_at_50%_0%,#000_30%,transparent_75%)] dark:block"
        style={{
          backgroundImage:
            "linear-gradient(#1e293b 1px, transparent 1px), linear-gradient(90deg, #1e293b 1px, transparent 1px)",
          backgroundSize: "48px 48px"
        }}
      />
      <div className="relative mx-auto grid w-full max-w-6xl items-center gap-14 px-6 pb-20 pt-16 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-cyan-600/30 bg-cyan-50 px-3 py-1.5 text-xs font-bold tracking-wider text-cyan-800 dark:border-cyan-400/30 dark:bg-cyan-950/60 dark:text-cyan-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 ring-3 ring-emerald-100 dark:ring-emerald-900" />
            실서비스 가동 중 · qaaimsync.com
          </span>
          <h1 className="mt-5 break-keep text-balance text-4xl font-black leading-tight tracking-tight text-slate-900 sm:text-5xl dark:text-white">
            <span className="mb-2 block text-2xl font-bold tracking-tight text-slate-500 sm:text-3xl dark:text-slate-400">
              이번 배포, 이전보다 나아졌을까?
            </span>
            감이 아니라 <em className="not-italic text-cyan-600 dark:text-cyan-400">근거로</em> 답하는
            <br />
            배포 품질 모니터링
          </h1>
          <p className="mt-5 max-w-xl break-keep text-lg leading-8 text-slate-600 dark:text-slate-300">
            가용성 · SSL · Lighthouse 성능 · 핵심 사용자 흐름을 검사 한 번에 측정하고, 이전
            배포와 자동 비교해 점수와 AI 진단으로 알려드립니다.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-cyan-600/30 transition hover:-translate-y-0.5 hover:bg-cyan-700"
              href="/signup"
            >
              무료로 시작하기 →
            </Link>
            <a
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-400 hover:text-cyan-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              href="#flow"
            >
              사용 흐름 보기 <span aria-hidden>↓</span>
            </a>
          </div>
          <div className="mt-7 flex flex-wrap gap-5 text-sm text-slate-500 dark:text-slate-400">
            <span>
              측정 카테고리 <b className="font-mono font-bold text-slate-900 dark:text-white">6</b>종
            </span>
            <span>
              시나리오 스텝 <b className="font-mono font-bold text-slate-900 dark:text-white">8</b>종
            </span>
            <span>
              배포 훅 연동 <b className="font-mono font-bold text-slate-900 dark:text-white">1</b>줄
            </span>
          </div>
        </div>

        <div aria-label="검사 리포트 미리보기" className="grid gap-3.5">
          <ScorePreviewCard />
          <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-xl shadow-slate-900/5 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-2 text-xs font-extrabold text-cyan-800 dark:text-cyan-300">
              <span className="inline-block h-2 w-2 rounded-sm bg-cyan-600" />
              AI 진단
            </div>
            <p className="mt-2 break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
              <b className="text-slate-900 dark:text-white">배포 후 성능이 소폭 개선되었습니다.</b> LCP가
              1.8s→1.6s로 줄었고, 로그인 흐름 8단계가 모두 통과했습니다. 조치가 필요한 이슈는
              없습니다.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-xl shadow-slate-900/5 dark:border-slate-800 dark:bg-slate-900">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#5865f2] text-base font-black text-white">
              D
            </span>
            <p className="text-slate-600 dark:text-slate-300">
              <b className="text-slate-900 dark:text-white">#aim-alerts</b> — ✅ 배포 검사 완료 · 종합{" "}
              <b className="text-slate-900 dark:text-white">97 A</b> · 회귀 없음
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}

function ScorePreviewCard() {
  return (
    <div className="flex items-center gap-5 rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-xl shadow-slate-900/5 dark:border-slate-800 dark:bg-slate-900">
      <div
        className="grid h-21 w-21 shrink-0 place-items-center rounded-full"
        style={{ background: "conic-gradient(#10b981 349deg, #e2e8f0 0)" }}
      >
        <div className="grid h-16 w-16 place-items-center rounded-full bg-white text-center font-mono dark:bg-slate-900">
          <span className="text-2xl font-extrabold leading-none text-slate-900 dark:text-white">
            97
            <small className="block text-[11px] font-extrabold text-emerald-600">A</small>
          </span>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">qaaimsync.com · 검사 리포트</h3>
          <span className="whitespace-nowrap rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-extrabold text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
            회귀 없음
          </span>
        </div>
        <div className="mt-2.5 flex flex-wrap gap-2 font-mono text-[11.5px] tabular-nums text-slate-500 dark:text-slate-400">
          <span className="rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700">
            성능 <b className="text-emerald-600 dark:text-emerald-400">+2 ▲</b>
          </span>
          <span className="rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700">
            응답 <b className="text-emerald-600 dark:text-emerald-400">-31ms ▲</b>
          </span>
          <span className="rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700">접근성 100</span>
          <span className="rounded-lg border border-slate-200 px-2 py-1 dark:border-slate-700">
            시나리오 <b className="text-emerald-600 dark:text-emerald-400">8/8 ✓</b>
          </span>
        </div>
      </div>
    </div>
  );
}

const FLOW_STEPS = [
  {
    no: "1",
    title: "계정 만들기",
    time: "~1분",
    body: "이메일과 비밀번호면 충분합니다. 인증 메일의 링크를 열면 바로 로그인할 수 있습니다.",
    mock: <SignupMock />
  },
  {
    no: "2",
    title: "서비스 등록",
    time: "~3분",
    body: "모니터링할 서비스의 URL을 등록하고, 메타 태그 한 줄로 도메인 소유를 확인합니다.",
    mock: <ProjectMock />
  },
  {
    no: "3",
    title: "검사 실행",
    time: "클릭 한 번",
    body: "버튼 한 번으로 시작하고, 익숙해지면 정기 검사나 CI 배포 훅으로 자동화하세요.",
    mock: <CheckRunMock />
  },
  {
    no: "4",
    title: "결과 확인",
    time: "자동",
    body: "6개 카테고리 점수와 등급, 이전 배포 대비 변화, 근거가 연결된 AI 진단까지. 문제가 생기면 webhook으로 먼저 알려드립니다.",
    mock: <ResultMock />
  }
];

function FlowSection() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 py-20" id="flow">
      <div className="max-w-xl">
        <div className="text-xs font-extrabold tracking-[0.14em] text-cyan-800 dark:text-cyan-300">사용 흐름</div>
        <h2 className="mt-2 break-keep text-balance text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-white">
          가입부터 첫 리포트까지, 4단계면 끝납니다
        </h2>
        <p className="mt-3 break-keep text-slate-600 dark:text-slate-300">
          각 단계에서 실제로 보게 될 화면입니다. 처음 오셔도 다음에 뭘 해야 하는지 헤매지
          않도록 설계했습니다.
        </p>
      </div>

      <div className="relative mt-12 grid gap-11">
        <div
          aria-hidden
          className="absolute bottom-7 left-[27px] top-7 border-l-2 border-dashed border-cyan-600/40"
        />
        {FLOW_STEPS.map((step) => (
          <div
            className="grid grid-cols-[56px_1fr] items-start gap-5 lg:grid-cols-[56px_1fr_1.15fr]"
            key={step.no}
          >
            <div className="relative z-10 grid h-14 w-14 place-items-center rounded-2xl border border-slate-200 bg-white font-mono text-lg font-extrabold text-cyan-800 shadow-md shadow-slate-900/10 dark:border-slate-700 dark:bg-slate-900 dark:text-cyan-300">
              {step.no}
            </div>
            <div>
              <h3 className="text-lg font-extrabold tracking-tight text-slate-900 dark:text-white">
                {step.title}
                <span className="ml-2 rounded-md bg-cyan-50 px-1.5 py-0.5 align-[2px] font-mono text-[11px] font-bold text-cyan-800 dark:bg-cyan-950 dark:text-cyan-300">
                  {step.time}
                </span>
              </h3>
              <p className="mt-2 max-w-md break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
                {step.body}
              </p>
            </div>
            <div className="col-start-2 lg:col-start-3">{step.mock}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MockFrame({ children, url }: { children: React.ReactNode; url: string }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white text-xs shadow-2xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-1.5 border-b border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/60">
        <i className="h-2 w-2 rounded-full bg-slate-200 dark:bg-slate-600" />
        <i className="h-2 w-2 rounded-full bg-slate-200 dark:bg-slate-600" />
        <i className="h-2 w-2 rounded-full bg-slate-200 dark:bg-slate-600" />
        <span className="ml-2 rounded-md border border-slate-200 bg-white px-2.5 py-0.5 font-mono text-[10.5px] text-slate-400 dark:border-slate-700 dark:bg-slate-900">
          {url}
        </span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function SignupMock() {
  return (
    <MockFrame url="qaaimsync.com/signup">
      <div className="text-[11px] font-bold text-slate-400 dark:text-slate-500">이메일</div>
      <div className="mt-1 rounded-lg border border-slate-200 px-3 py-2 text-slate-500 dark:border-slate-700 dark:text-slate-400">
        you@example.com
      </div>
      <div className="mt-3 rounded-lg bg-cyan-600 py-2 text-center font-extrabold text-white">
        가입하기
      </div>
      <div className="mt-2.5 rounded-lg bg-emerald-50 px-3 py-2 font-semibold text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
        ✉️ 인증 메일을 보냈습니다 — 링크를 열면 완료됩니다.
      </div>
    </MockFrame>
  );
}

function ProjectMock() {
  return (
    <MockFrame url="projects/new">
      <div className="text-[11px] font-bold text-slate-400 dark:text-slate-500">서비스 URL</div>
      <div className="mt-1 rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-500 dark:border-slate-700 dark:text-slate-400">
        https://myservice.io
      </div>
      <div className="mt-2.5 text-[11px] font-bold text-slate-400 dark:text-slate-500">소유 확인 — head에 한 줄</div>
      <div className="mt-1 overflow-x-auto rounded-lg border border-slate-200 px-3 py-2 font-mono text-[10.5px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
        {'<meta name="aim-verification" content="a1b2…">'}
      </div>
      <div className="mt-2.5 rounded-lg bg-emerald-50 px-3 py-2 font-semibold text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400">
        ✓ 도메인 확인 완료 — 검사를 시작할 수 있습니다.
      </div>
    </MockFrame>
  );
}

function CheckRunMock() {
  return (
    <MockFrame url="check-runs">
      <div className="flex items-center justify-between border-b border-dashed border-slate-200 py-2 dark:border-slate-700">
        <span className="text-slate-600 dark:text-slate-300">가용성 · SSL</span>
        <span className="rounded-md border border-cyan-600/25 bg-cyan-50 px-2 py-0.5 font-mono text-[10.5px] text-cyan-800 dark:bg-cyan-950 dark:text-cyan-300">
          완료 200 OK
        </span>
      </div>
      <div className="flex items-center justify-between border-b border-dashed border-slate-200 py-2 dark:border-slate-700">
        <span className="text-slate-600 dark:text-slate-300">Lighthouse 모바일</span>
        <span className="rounded-md border border-cyan-600/25 bg-cyan-50 px-2 py-0.5 font-mono text-[10.5px] text-cyan-800 dark:bg-cyan-950 dark:text-cyan-300">
          측정 중…
        </span>
      </div>
      <div className="flex items-center justify-between py-2">
        <span className="text-slate-600 dark:text-slate-300">사용자 흐름 8단계</span>
        <span className="rounded-md border border-slate-200 px-2 py-0.5 font-mono text-[10.5px] text-slate-400 dark:border-slate-700">
          대기
        </span>
      </div>
      <div className="mt-3 rounded-lg bg-cyan-600 py-2 text-center font-extrabold text-white">
        검사 실행 ▶
      </div>
    </MockFrame>
  );
}

function ResultMock() {
  return (
    <MockFrame url="runs/164">
      <div className="flex items-center justify-between border-b border-dashed border-slate-200 pb-2 dark:border-slate-700">
        <b className="font-mono text-xl text-slate-900 dark:text-white">
          97 <span className="text-emerald-600 dark:text-emerald-400">A</span>
        </b>
        <svg aria-hidden className="block" height="34" viewBox="0 0 150 34" width="150">
          <polyline
            fill="none"
            points="0,22 25,20 50,24 75,14 100,15 125,9 150,6"
            stroke="#0891b2"
            strokeLinecap="round"
            strokeWidth="2.5"
          />
          <circle cx="150" cy="6" fill="#0891b2" r="3.5" />
        </svg>
      </div>
      <div className="flex items-center justify-between border-b border-dashed border-slate-200 py-2 dark:border-slate-700">
        <span className="font-mono tabular-nums text-slate-600 dark:text-slate-300">
          성능 86 · 접근성 100 · SEO 100
        </span>
        <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-extrabold text-emerald-600">
          회귀 없음
        </span>
      </div>
      <div className="flex items-center justify-between pt-2">
        <span className="text-slate-600 dark:text-slate-300">직전 배포 대비</span>
        <span className="font-mono font-bold text-emerald-600">+2.0 ▲</span>
      </div>
    </MockFrame>
  );
}

const FEATURES = [
  {
    k: "SCORE",
    title: "결정론적 스코어링",
    body: "6개 카테고리 가중 평균과 risk gate. 산출 근거까지 저장되어 재현 가능합니다."
  },
  {
    k: "FLOW",
    title: "사용자 흐름 테스트",
    body: "클릭·입력·검증 8종 스텝으로 핵심 흐름을 정의하면 실패 시 스크린샷·콘솔·네트워크 근거를 자동 수집합니다."
  },
  {
    k: "DIFF",
    title: "회귀 감지",
    body: "직전 실행·베이스라인 대비 점수와 응답시간 변화를 추적합니다. “느려졌는지”를 숫자로 봅니다."
  },
  {
    k: "AI",
    title: "AI 진단 리포트",
    body: "수집된 근거만으로 원인과 조치를 한국어로 서술합니다. 판단은 코드가, 설명은 AI가."
  },
  {
    k: "PERF",
    title: "Lighthouse 성능",
    body: "모바일 기준 성능·접근성·SEO를 검사마다 측정하고 추이를 쌓습니다."
  },
  {
    k: "DEPLOY",
    title: "배포 훅",
    body: "CI에 curl 한 줄. 배포 직후 자동 검사로 커밋 SHA별 품질 기록이 남습니다."
  }
];

function FeatureSection() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 pb-20" id="features">
      <div className="max-w-xl">
        <div className="text-xs font-extrabold tracking-[0.14em] text-cyan-800 dark:text-cyan-300">
          무엇을 측정하나
        </div>
        <h2 className="mt-2 break-keep text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-white">
          uptime 체커가 놓치는 것까지
        </h2>
      </div>
      <div className="mt-10 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <div
            className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-cyan-600/45 dark:border-slate-800 dark:bg-slate-900"
            key={feature.k}
          >
            <div className="font-mono text-[11px] font-bold text-cyan-800 dark:text-cyan-300">{feature.k}</div>
            <h3 className="mt-2 text-base font-extrabold text-slate-900 dark:text-white">{feature.title}</h3>
            <p className="mt-1.5 break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">{feature.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="mx-auto w-full max-w-6xl px-6 pb-4">
      <div className="relative flex flex-wrap items-center justify-between gap-6 overflow-hidden rounded-3xl bg-slate-900 px-10 py-12 text-white dark:ring-1 dark:ring-slate-800">
        <div
          aria-hidden
          className="absolute -right-16 -top-16 h-64 w-64 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(8,145,178,.5), transparent 70%)" }}
        />
        <div>
          <h2 className="break-keep text-2xl font-black tracking-tight sm:text-3xl">
            다음 배포부터, 품질을 기록하세요
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            가입 1분 · 무료 · AIM은 AIM 자신을 모니터링하며 운영 중입니다
          </p>
        </div>
        <Link
          className="relative z-10 inline-flex items-center rounded-xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-cyan-600/40 transition hover:-translate-y-0.5 hover:bg-cyan-500"
          href="/signup"
        >
          무료로 시작하기 →
        </Link>
      </div>
    </section>
  );
}
