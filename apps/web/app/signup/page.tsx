"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { getApiBaseUrl, loginUser, signupUser } from "@/lib/api";
import { storeAccessToken } from "@/lib/auth";

const MIN_PASSWORD_LENGTH = 8;

type SignupState =
  | "idle"
  | "submitting"
  | "success"
  | "invalid"
  | "password-mismatch"
  | "email-already-registered"
  | "login-unavailable"
  | "unavailable";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [signupState, setSignupState] = useState<SignupState>("idle");

  const apiBaseUrlLabel = useMemo(() => {
    try {
      return getApiBaseUrl();
    } catch {
      return "잘못된 NEXT_PUBLIC_API_URL";
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || password.length < MIN_PASSWORD_LENGTH) {
      setSignupState("invalid");
      return;
    }

    if (password !== confirmPassword) {
      setSignupState("password-mismatch");
      return;
    }

    setSignupState("submitting");
    const signupResult = await signupUser({
      payload: {
        email: normalizedEmail,
        password
      }
    });

    if (signupResult.state !== "success") {
      setSignupState(signupResult.state);
      return;
    }

    const loginResult = await loginUser({
      email: normalizedEmail,
      password
    });

    if (loginResult.state !== "success") {
      setSignupState("login-unavailable");
      return;
    }

    storeAccessToken(loginResult.accessToken);
    setSignupState("success");
    router.replace("/projects/new");
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-12">
        <div className="grid w-full gap-8 lg:grid-cols-[1fr_460px] lg:items-center">
          <div>
            <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
              AIM Signup
            </p>
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
              계정을 만들고 첫 서비스를 바로 등록하세요
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-300">
              AIM은 가입 후 첫 Project를 만들고, domain verification을 거친 뒤 CheckRun을
              시작하는 흐름을 기준으로 설계되어 있습니다. 가입이 완료되면 자동으로 로그인하고
              Project 생성 화면으로 이동합니다.
            </p>

            <div className="mt-8 grid gap-3 text-sm text-slate-300">
              <OnboardingStep index={1} text="Email/password 계정을 생성합니다." />
              <OnboardingStep index={2} text="JWT access token을 브라우저에 저장합니다." />
              <OnboardingStep index={3} text="첫 Project 생성 화면으로 이동합니다." />
              <OnboardingStep
                index={4}
                text="HTML meta-tag 기반 domain verification을 진행합니다."
              />
            </div>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                className="inline-flex rounded-2xl border border-white/10 px-5 py-3 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
                href="/login"
              >
                이미 계정이 있어요
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
              <h2 className="text-2xl font-bold text-slate-100">회원가입</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                요청 대상 API는 <code className="text-cyan-200">{apiBaseUrlLabel}</code>입니다.
                원문 비밀번호는 화면에 저장하지 않고 Auth API로만 전송합니다.
              </p>
            </div>

            <div className="mt-6 space-y-4">
              <label className="block" htmlFor="signup-email">
                <span className="text-sm font-semibold text-slate-300">Email</span>
                <input
                  autoComplete="email"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
                  id="signup-email"
                  name="email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  required
                  type="email"
                  value={email}
                />
              </label>

              <label className="block" htmlFor="signup-password">
                <span className="text-sm font-semibold text-slate-300">Password</span>
                <input
                  autoComplete="new-password"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
                  id="signup-password"
                  minLength={MIN_PASSWORD_LENGTH}
                  name="password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="8자 이상"
                  required
                  type="password"
                  value={password}
                />
              </label>

              <label className="block" htmlFor="signup-confirm-password">
                <span className="text-sm font-semibold text-slate-300">Confirm password</span>
                <input
                  autoComplete="new-password"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
                  id="signup-confirm-password"
                  minLength={MIN_PASSWORD_LENGTH}
                  name="confirm_password"
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="비밀번호 확인"
                  required
                  type="password"
                  value={confirmPassword}
                />
              </label>
            </div>

            <button
              className="mt-6 w-full rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={signupState === "submitting"}
              type="submit"
            >
              {signupState === "submitting" ? "가입 처리 중" : "가입하고 첫 Project 만들기"}
            </button>

            <SignupNotice signupState={signupState} />
          </form>
        </div>
      </section>
    </main>
  );
}

function OnboardingStep({ index, text }: { index: number; text: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan-300 text-xs font-black text-slate-950">
        {index}
      </span>
      <p>{text}</p>
    </div>
  );
}

function SignupNotice({ signupState }: { signupState: SignupState }) {
  if (signupState === "idle" || signupState === "submitting") {
    return null;
  }

  const notice = signupStateMessage[signupState];

  return (
    <p
      className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
        signupState === "success"
          ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
          : "border-rose-400/20 bg-rose-400/10 text-rose-100"
      }`}
    >
      {notice}
    </p>
  );
}

const signupStateMessage: Record<Exclude<SignupState, "idle" | "submitting">, string> = {
  success: "가입되었습니다. 첫 Project 생성 화면으로 이동합니다.",
  invalid: "이메일 형식과 8자 이상 비밀번호를 확인하세요.",
  "password-mismatch": "비밀번호와 비밀번호 확인 값이 다릅니다.",
  "email-already-registered": "이미 등록된 이메일입니다. 로그인 화면에서 로그인하세요.",
  "login-unavailable":
    "계정은 생성되었지만 자동 로그인에 실패했습니다. 로그인 화면에서 다시 로그인하세요.",
  unavailable: "회원가입 요청에 실패했습니다. API 서버 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
};
