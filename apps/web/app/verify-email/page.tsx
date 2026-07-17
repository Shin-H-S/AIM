"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { confirmEmailVerification, requestEmailVerification } from "@/lib/api";

type ConfirmState = "verifying" | "success" | "invalid-token" | "unavailable";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  if (!token) {
    return (
      <PageShell>
        <ResendForm
          description="가입 시 사용한 이메일을 입력하면 인증 메일을 다시 보내드립니다."
          title="인증 메일 다시 받기"
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <TokenConfirm token={token} />
    </PageShell>
  );
}

function TokenConfirm({ token }: { token: string }) {
  const [confirmState, setConfirmState] = useState<ConfirmState>("verifying");

  useEffect(() => {
    let cancelled = false;

    confirmEmailVerification({ token }).then((result) => {
      if (cancelled) {
        return;
      }
      setConfirmState(result.state === "success" ? "success" : result.state);
    });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (confirmState === "verifying") {
    return (
      <>
        <h1 className="text-2xl font-bold text-slate-900">이메일 인증 중</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">잠시만 기다려주세요.</p>
      </>
    );
  }

  if (confirmState === "success") {
    return (
      <>
        <h1 className="text-2xl font-bold text-slate-900">이메일 인증이 완료되었습니다</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          이제 로그인해서 첫 Project를 만들 수 있습니다.
        </p>
        <Link
          className="mt-6 inline-flex rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-600"
          href="/login"
        >
          로그인으로 이동
        </Link>
      </>
    );
  }

  if (confirmState === "invalid-token") {
    return (
      <ResendForm
        description="인증 링크가 만료되었거나 이미 사용되었습니다. 이메일을 입력하면 새 인증 메일을 보내드립니다."
        title="인증 링크가 유효하지 않습니다"
      />
    );
  }

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">인증 요청에 실패했습니다</h1>
      <p className="mt-2 text-sm leading-6 text-slate-500">
        잠시 후 페이지를 새로고침해 다시 시도하세요.
      </p>
    </>
  );
}

type ResendState = "idle" | "submitting" | "accepted" | "invalid" | "unavailable";

function ResendForm({ description, title }: { description: string; title: string }) {
  const [email, setEmail] = useState("");
  const [resendState, setResendState] = useState<ResendState>("idle");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      setResendState("invalid");
      return;
    }

    setResendState("submitting");
    const result = await requestEmailVerification({ email: normalizedEmail });
    setResendState(result.state === "accepted" ? "accepted" : "unavailable");
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>

      <label className="mt-6 block" htmlFor="verify-email-address">
        <span className="text-sm font-semibold text-slate-600">이메일</span>
        <input
          autoComplete="email"
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
          id="verify-email-address"
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          required
          type="email"
          value={email}
        />
      </label>

      <button
        className="mt-6 w-full rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={resendState === "submitting"}
        type="submit"
      >
        {resendState === "submitting" ? "발송 중" : "인증 메일 보내기"}
      </button>

      <ResendNotice resendState={resendState} />
    </form>
  );
}

function ResendNotice({ resendState }: { resendState: ResendState }) {
  if (resendState === "idle" || resendState === "submitting") {
    return null;
  }

  if (resendState === "accepted") {
    return (
      <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-800">
        등록된 미인증 계정이라면 인증 메일이 발송됩니다. 메일함을 확인하세요.
      </p>
    );
  }

  const message =
    resendState === "invalid"
      ? "이메일 형식을 확인하세요."
      : "요청에 실패했습니다. 잠시 후 다시 시도하세요.";

  return (
    <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
      {message}
    </p>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl justify-center px-6 py-12">
        <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60">
          {children}
        </div>
      </section>
    </main>
  );
}
