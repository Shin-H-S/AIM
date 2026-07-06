"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { loginUser } from "@/lib/api";
import { getStoredAccessToken, storeAccessToken } from "@/lib/auth";

type LoginState = "idle" | "submitting" | "success" | "invalid-credentials" | "unavailable";

export default function Home() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginState, setLoginState] = useState<LoginState>("idle");

  useEffect(() => {
    if (getStoredAccessToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!email.trim() || !password) {
      setLoginState("invalid-credentials");
      return;
    }

    setLoginState("submitting");
    const result = await loginUser({
      email,
      password
    });

    if (result.state !== "success") {
      setLoginState(result.state);
      return;
    }

    storeAccessToken(result.accessToken);
    setLoginState("success");
    router.replace("/dashboard");
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl items-center px-6 py-12">
        <div className="grid w-full gap-8 lg:grid-cols-[1fr_460px] lg:items-center">
          <div>
            <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-700">
              AI Manager
            </p>
            <h1 className="break-keep text-balance text-3xl font-bold tracking-tight text-cyan-600 sm:text-5xl">
              <span className="text-4xl font-black tracking-tight text-slate-900 sm:text-6xl">
                AIM<span className="text-cyan-600">.</span>
              </span>
              이 검사하고, 진단하고, 처방합니다.
            </h1>
            <p className="mt-6 max-w-3xl break-keep text-lg leading-8 text-slate-600">
              AIM은 배포 후 서비스가 실제로 안정적인지 검사하고, 문제의 원인과 개선
              방법까지 알려줍니다. 로그인하면 프로젝트의 검사 상태와 AI 진단 결과를 바로
              확인할 수 있습니다.
            </p>
          </div>

          <form
            className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60"
            onSubmit={handleSubmit}
          >
            <div>
              <h2 className="text-2xl font-bold text-slate-900">로그인</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                비밀번호는 저장되지 않고 인증에만 사용됩니다.
              </p>
            </div>

            <div className="mt-6 space-y-4">
              <label className="block" htmlFor="email">
                <span className="text-sm font-semibold text-slate-600">Email</span>
                <input
                  autoComplete="email"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
                  id="email"
                  name="email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  type="email"
                  value={email}
                />
              </label>

              <label className="block" htmlFor="password">
                <span className="text-sm font-semibold text-slate-600">Password</span>
                <input
                  autoComplete="current-password"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
                  id="password"
                  name="password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="비밀번호"
                  type="password"
                  value={password}
                />
              </label>
            </div>

            <button
              className="mt-6 w-full rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={loginState === "submitting"}
              type="submit"
            >
              {loginState === "submitting" ? "로그인 중" : "로그인"}
            </button>

            <p className="mt-4 text-center text-sm text-slate-500">
              계정이 없나요?{" "}
              <Link className="font-bold text-cyan-700 hover:text-cyan-700" href="/signup">
                회원가입
              </Link>
            </p>

            <LoginNotice loginState={loginState} />
          </form>
        </div>
      </section>
    </main>
  );
}

function LoginNotice({ loginState }: { loginState: LoginState }) {
  if (loginState === "idle" || loginState === "submitting") {
    return null;
  }

  if (loginState === "success") {
    return (
      <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-800">
        로그인되었습니다. Dashboard로 이동합니다.
      </p>
    );
  }

  if (loginState === "invalid-credentials") {
    return (
      <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
        이메일 또는 비밀번호를 확인하세요.
      </p>
    );
  }

  return (
    <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
      로그인 요청에 실패했습니다. 잠시 후 다시 시도하세요.
    </p>
  );
}
