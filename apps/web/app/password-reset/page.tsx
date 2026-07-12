"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { requestPasswordReset } from "@/lib/api";

type RequestState = "idle" | "submitting" | "accepted" | "invalid" | "unavailable";

export default function PasswordResetRequestPage() {
  const [email, setEmail] = useState("");
  const [requestState, setRequestState] = useState<RequestState>("idle");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!email.trim()) {
      setRequestState("invalid");
      return;
    }

    setRequestState("submitting");
    const result = await requestPasswordReset({ email });
    setRequestState(result.state === "accepted" ? "accepted" : "unavailable");
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl justify-center px-6 py-12">
        <form
          className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60"
          onSubmit={handleSubmit}
        >
          <h1 className="text-2xl font-bold text-slate-900">비밀번호 재설정</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            가입한 이메일 주소를 입력하면 재설정 링크를 보내드립니다.
          </p>

          <label className="mt-6 block" htmlFor="email">
            <span className="text-sm font-semibold text-slate-600">이메일</span>
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

          <button
            className="mt-6 w-full rounded-2xl bg-cyan-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={requestState === "submitting"}
            type="submit"
          >
            {requestState === "submitting" ? "요청 중" : "재설정 메일 보내기"}
          </button>

          <p className="mt-4 text-center text-sm text-slate-500">
            비밀번호가 기억나셨나요?{" "}
            <Link className="font-bold text-cyan-700 hover:text-cyan-700" href="/">
              로그인으로 돌아가기
            </Link>
          </p>

          <RequestNotice requestState={requestState} />
        </form>
      </section>
    </main>
  );
}

function RequestNotice({ requestState }: { requestState: RequestState }) {
  if (requestState === "idle" || requestState === "submitting") {
    return null;
  }

  if (requestState === "accepted") {
    return (
      <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-800">
        입력한 주소가 가입된 이메일이라면 재설정 링크를 보냈습니다. 메일함(스팸함 포함)을
        확인하세요. 링크는 30분 동안 유효합니다.
      </p>
    );
  }

  if (requestState === "invalid") {
    return (
      <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
        이메일 주소를 입력하세요.
      </p>
    );
  }

  return (
    <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
      요청에 실패했습니다. 잠시 후 다시 시도하세요.
    </p>
  );
}
