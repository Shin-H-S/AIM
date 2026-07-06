"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCurrentUser, logoutUser, type User } from "@/lib/api";
import {
  ACCESS_TOKEN_CHANGE_EVENT,
  clearStoredAccessToken,
  getStoredAccessToken
} from "@/lib/auth";

type SessionState =
  | { state: "loading" }
  | { state: "signed-out" }
  | { state: "signed-in"; user: User | null };

export function AppHeader() {
  const [session, setSession] = useState<SessionState>({ state: "loading" });
  const lastSyncedTokenRef = useRef<string | null | undefined>(undefined);

  const syncSession = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (accessToken === lastSyncedTokenRef.current) {
      return;
    }

    lastSyncedTokenRef.current = accessToken;

    if (!accessToken) {
      setSession({ state: "signed-out" });
      return;
    }

    const result = await fetchCurrentUser({ accessToken });

    if (result.state === "unauthorized") {
      clearStoredAccessToken();
      setSession({ state: "signed-out" });
      return;
    }

    setSession({
      state: "signed-in",
      user: result.state === "success" ? result.user : null
    });
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void syncSession();
    });

    const handleTokenChange = () => {
      void syncSession();
    };

    window.addEventListener(ACCESS_TOKEN_CHANGE_EVENT, handleTokenChange);
    window.addEventListener("storage", handleTokenChange);

    return () => {
      window.removeEventListener(ACCESS_TOKEN_CHANGE_EVENT, handleTokenChange);
      window.removeEventListener("storage", handleTokenChange);
    };
  }, [syncSession]);

  function handleLogout() {
    const accessToken = getStoredAccessToken();

    if (accessToken) {
      void logoutUser({ accessToken });
    }

    clearStoredAccessToken();
    window.location.assign("/");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-3">
        <div className="flex items-center gap-4">
          <Link
            className="text-lg font-black tracking-tight text-slate-900"
            href={session.state === "signed-in" ? "/dashboard" : "/"}
          >
            AIM<span className="text-cyan-600">.</span>
          </Link>
          {session.state === "signed-in" && (
            <nav className="flex items-center gap-1 text-sm font-semibold text-slate-600">
              <Link
                className="rounded-xl px-3 py-1.5 transition hover:bg-slate-100 hover:text-cyan-700"
                href="/dashboard"
              >
                Dashboard
              </Link>
              <Link
                className="rounded-xl px-3 py-1.5 transition hover:bg-slate-100 hover:text-cyan-700"
                href="/projects/new"
              >
                새 Project
              </Link>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-2">
          {session.state === "signed-out" && (
            <>
              <Link
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:border-cyan-400 hover:text-cyan-700"
                href="/"
              >
                로그인
              </Link>
              <Link
                className="rounded-xl bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-cyan-500"
                href="/signup"
              >
                회원가입
              </Link>
            </>
          )}
          {session.state === "signed-in" && (
            <>
              <span className="hidden rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 ring-1 ring-emerald-200 sm:inline">
                {session.user?.email ?? "로그인됨"}
              </span>
              <button
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:border-cyan-400 hover:text-cyan-700"
                onClick={handleLogout}
                type="button"
              >
                로그아웃
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
