"use client";

import { useEffect, useState } from "react";
import { fetchApiHealth, getApiBaseUrl, type HealthCheckResult } from "@/lib/api";

const statusCopy: Record<HealthCheckResult["state"], string> = {
  loading: "확인 중",
  available: "연결됨",
  unavailable: "연결 실패"
};

export default function Home() {
  const [health, setHealth] = useState<HealthCheckResult>({
    state: "loading"
  });

  useEffect(() => {
    let isMounted = true;

    fetchApiHealth().then((result) => {
      if (isMounted) {
        setHealth(result);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-6 py-16">
        <div className="mb-10 max-w-3xl">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
            AIM MVP Foundation
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            배포 후 서비스 품질을 근거로 확인하는 대시보드
          </h1>
          <p className="mt-6 text-lg leading-8 text-slate-300">
            AIM은 가용성, Lighthouse 품질 지표, 핵심 사용자 흐름, 이전 실행 대비 회귀를
            모아 배포 위험을 판단하는 품질 평가·모니터링 플랫폼입니다.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <StatusCard health={health} />
          <FeatureCard
            title="검사 대상"
            description="프로젝트와 서비스 URL을 등록하고 소유권 확인 후 반복 검사를 실행합니다."
          />
          <FeatureCard
            title="다음 단계"
            description="프로젝트 CRUD와 인증을 붙여 실제 사용자별 대시보드로 확장합니다."
          />
        </div>
      </section>
    </main>
  );
}

function StatusCard({ health }: { health: HealthCheckResult }) {
  const isAvailable = health.state === "available";
  const apiBaseUrlLabel = getApiBaseUrlLabel();
  const badgeClassName = isAvailable
    ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
    : health.state === "loading"
      ? "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20"
      : "bg-rose-400/10 text-rose-300 ring-rose-400/20";

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">API 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${badgeClassName}`}>
          {statusCopy[health.state]}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-300">
        프론트엔드는 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의{" "}
        <code className="text-cyan-200">/health</code> 응답을 확인합니다.
      </p>
      <p className="mt-4 text-sm text-slate-400">
        {health.state === "available" && `서비스: ${health.service}`}
        {health.state === "loading" && "FastAPI 서버 상태를 불러오는 중입니다."}
        {health.state === "unavailable" &&
          "API 서버가 실행 중인지, NEXT_PUBLIC_API_URL 값이 맞는지 확인하세요."}
      </p>
    </article>
  );
}

function getApiBaseUrlLabel() {
  try {
    return getApiBaseUrl();
  } catch {
    return "잘못된 NEXT_PUBLIC_API_URL";
  }
}

function FeatureCard({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-4 text-sm leading-6 text-slate-300">{description}</p>
    </article>
  );
}
