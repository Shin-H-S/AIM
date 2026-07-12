"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { confirmPasswordReset } from "@/lib/api";

type ConfirmState =
  | "idle"
  | "submitting"
  | "success"
  | "password-mismatch"
  | "password-too-short"
  | "invalid-token"
  | "unavailable";

export default function PasswordResetConfirmPage() {
  return (
    <Suspense fallback={null}>
      <PasswordResetConfirmForm />
    </Suspense>
  );
}

function PasswordResetConfirmForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmState, setConfirmState] = useState<ConfirmState>("idle");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (newPassword.length < 8) {
      setConfirmState("password-too-short");
      return;
    }

    if (newPassword !== confirmPassword) {
      setConfirmState("password-mismatch");
      return;
    }

    setConfirmState("submitting");
    const result = await confirmPasswordReset({ token, newPassword });

    if (result.state === "success") {
      setConfirmState("success");
      return;
    }

    setConfirmState(result.state === "invalid-token" ? "invalid-token" : "unavailable");
  }

  if (!token) {
    return (
      <PageShell>
        <h1 className="text-2xl font-bold text-slate-900">재설정 링크가 올바르지 않습니다</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          메일에 포함된 링크로 다시 접속하거나, 재설정 메일을 새로 요청하세요.
        </p>
        <Link
          className="mt-6 inline-flex rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500"
          href="/password-reset"
        >
          재설정 메일 다시 요청
        </Link>
      </PageShell>
    );
  }

  if (confirmState === "success") {
    return (
      <PageShell>
        <h1 className="text-2xl font-bold text-slate-900">비밀번호가 변경되었습니다</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          새 비밀번호로 다시 로그인하세요.
        </p>
        <Link
          className="mt-6 inline-flex rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500"
          href="/"
        >
          로그인으로 이동
        </Link>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <form onSubmit={handleSubmit}>
        <h1 className="text-2xl font-bold text-slate-900">새 비밀번호 설정</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          사용할 새 비밀번호를 입력하세요. 8자 이상이어야 합니다.
        </p>

        <div className="mt-6 space-y-4">
          <label className="block" htmlFor="new-password">
            <span className="text-sm font-semibold text-slate-600">새 비밀번호</span>
            <input
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
              id="new-password"
              name="new-password"
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="8자 이상"
              type="password"
              value={newPassword}
            />
          </label>

          <label className="block" htmlFor="confirm-password">
            <span className="text-sm font-semibold text-slate-600">새 비밀번호 확인</span>
            <input
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
              id="confirm-password"
              name="confirm-password"
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="다시 입력"
              type="password"
              value={confirmPassword}
            />
          </label>
        </div>

        <button
          className="mt-6 w-full rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={confirmState === "submitting"}
          type="submit"
        >
          {confirmState === "submitting" ? "변경 중" : "비밀번호 변경"}
        </button>

        <ConfirmNotice confirmState={confirmState} />
      </form>
    </PageShell>
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

function ConfirmNotice({ confirmState }: { confirmState: ConfirmState }) {
  if (confirmState === "idle" || confirmState === "submitting" || confirmState === "success") {
    return null;
  }

  const message =
    confirmState === "password-too-short"
      ? "비밀번호는 8자 이상이어야 합니다."
      : confirmState === "password-mismatch"
        ? "두 비밀번호가 일치하지 않습니다."
        : confirmState === "invalid-token"
          ? "재설정 링크가 만료되었거나 이미 사용되었습니다. 메일을 다시 요청하세요."
          : "요청에 실패했습니다. 잠시 후 다시 시도하세요.";

  return (
    <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
      {message}
    </p>
  );
}
