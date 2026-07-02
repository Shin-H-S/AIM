"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { loginUser } from "@/lib/api";
import { storeAccessToken } from "@/lib/auth";

type LoginState = "idle" | "submitting" | "success" | "invalid-credentials" | "unavailable";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginState, setLoginState] = useState<LoginState>("idle");

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
    router.replace("/");
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-12">
        <div className="grid w-full gap-8 lg:grid-cols-[1fr_460px] lg:items-center">
          <div>
            <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
              AIM Login
            </p>
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
              로그인하고 프로젝트 상태를 바로 확인하세요
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-300">
              AIM Web은 FastAPI Auth에서 발급한 JWT access token을 브라우저에 저장하고,
              Project dashboard와 결과 화면 조회에 사용합니다. 아직 계정이 없다면 회원가입 후
              첫 Project 생성 화면으로 바로 이동할 수 있습니다.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                className="inline-flex rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
                href="/signup"
              >
                새 계정 만들기
              </Link>
              <Link
                className="inline-flex rounded-2xl border border-white/10 px-5 py-3 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
                href="/"
              >
                Dashboard로 돌아가기
              </Link>
            </div>
          </div>

          <form
            className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20"
            onSubmit={handleSubmit}
          >
            <div>
              <h2 className="text-2xl font-bold text-slate-100">로그인</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                이메일과 비밀번호는 API로만 전송되며 화면에 저장하지 않습니다. 저장되는 값은
                access token입니다.
              </p>
            </div>

            <div className="mt-6 space-y-4">
              <label className="block" htmlFor="email">
                <span className="text-sm font-semibold text-slate-300">Email</span>
                <input
                  autoComplete="email"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
                  id="email"
                  name="email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  type="email"
                  value={email}
                />
              </label>

              <label className="block" htmlFor="password">
                <span className="text-sm font-semibold text-slate-300">Password</span>
                <input
                  autoComplete="current-password"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
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
              className="mt-6 w-full rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={loginState === "submitting"}
              type="submit"
            >
              {loginState === "submitting" ? "로그인 중" : "로그인"}
            </button>

            <p className="mt-4 text-center text-sm text-slate-400">
              계정이 없나요?{" "}
              <Link className="font-bold text-cyan-200 hover:text-cyan-100" href="/signup">
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
      <p className="mt-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm leading-6 text-emerald-100">
        로그인되었습니다. Dashboard로 이동합니다.
      </p>
    );
  }

  if (loginState === "invalid-credentials") {
    return (
      <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100">
        이메일 또는 비밀번호를 확인하세요.
      </p>
    );
  }

  return (
    <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100">
      로그인 요청에 실패했습니다. API 서버 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요.
    </p>
  );
}
