"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCurrentUser, fetchProject, logoutUser, type User } from "@/lib/api";
import {
  ACCESS_TOKEN_CHANGE_EVENT,
  clearStoredAccessToken,
  getStoredAccessToken
} from "@/lib/auth";

type SessionState =
  | { state: "loading" }
  | { state: "signed-out" }
  | { state: "signed-in"; user: User | null };

// 프로젝트 하위 영역 로컬 탭. 헤더가 "지금 이 프로젝트의 어디"인지 보여주고
// 영역 간 이동을 페이지 내 링크 없이 바로 할 수 있게 한다(2026-07-18 내비 개선).
const PROJECT_SECTIONS = [
  { label: "검사", slug: "check-runs" },
  { label: "시나리오", slug: "scenarios" },
  { label: "알림", slug: "alerts" },
  { label: "설정", slug: "settings" }
] as const;

function parseProjectContext(
  pathname: string
): { projectId: string; section: string | null } | null {
  const match = pathname.match(/^\/projects\/([^/]+)(?:\/([^/]+))?/);
  if (!match || match[1] === "new") {
    return null;
  }

  return { projectId: match[1], section: match[2] ?? null };
}

export function AppHeader() {
  const pathname = usePathname();
  const [session, setSession] = useState<SessionState>({ state: "loading" });
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  // 프로젝트 이름 캐시. 조회 완료 시(비동기)에만 갱신되며, 같은 프로젝트는 재조회하지 않는다.
  const [projectNames, setProjectNames] = useState<Record<string, string>>({});
  const lastSyncedTokenRef = useRef<string | null | undefined>(undefined);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

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

  // 유저 메뉴 바깥 클릭·Escape로 닫기.
  useEffect(() => {
    if (!isUserMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsUserMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isUserMenuOpen]);

  const isSignedIn = session.state === "signed-in";
  const projectContext = isSignedIn ? parseProjectContext(pathname) : null;
  const contextProjectId = projectContext?.projectId ?? null;
  // 홈은 히어로가 섹션 안내를 담당하고 로그인·가입은 집중 화면이므로,
  // 이 페이지들에서는 비로그인 앵커 내비를 숨기고 로고+인증 버튼만 남긴다.
  const hideGuestNav = pathname === "/" || pathname === "/login" || pathname === "/signup";

  // 프로젝트 컨텍스트 배지에 쓸 이름 조회.
  useEffect(() => {
    if (!contextProjectId || !isSignedIn || projectNames[contextProjectId]) {
      return;
    }

    const accessToken = getStoredAccessToken();
    if (!accessToken) {
      return;
    }

    let cancelled = false;
    void fetchProject({ accessToken, projectId: contextProjectId }).then((result) => {
      if (cancelled || result.state !== "success") {
        return;
      }
      setProjectNames((names) => ({ ...names, [contextProjectId]: result.project.name }));
    });

    return () => {
      cancelled = true;
    };
  }, [contextProjectId, isSignedIn, projectNames]);

  const projectName = contextProjectId ? (projectNames[contextProjectId] ?? null) : null;

  function closeMobileMenu() {
    setIsMobileMenuOpen(false);
  }

  function handleLogout() {
    const accessToken = getStoredAccessToken();

    if (accessToken) {
      void logoutUser({ accessToken });
    }

    clearStoredAccessToken();
    window.location.assign("/");
  }

  const userEmail = session.state === "signed-in" ? (session.user?.email ?? null) : null;
  const avatarInitial = userEmail ? userEmail[0].toUpperCase() : "U";

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
        <div className="flex min-w-0 items-center gap-5">
          <Link
            className="shrink-0 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl"
            href={isSignedIn ? "/dashboard" : "/"}
          >
            AIM<span className="text-cyan-600">.</span>
          </Link>

          {session.state === "signed-out" && !hideGuestNav && (
            <nav className="hidden items-center gap-1 text-sm font-semibold text-slate-600 sm:flex">
              <Link className={navLinkClassName(false)} href="/#flow">
                사용 흐름
              </Link>
              <Link className={navLinkClassName(false)} href="/#features">
                기능
              </Link>
              <a
                className={navLinkClassName(false)}
                href="https://github.com/Shin-H-S/AIM"
                rel="noreferrer"
                target="_blank"
              >
                GitHub
              </a>
            </nav>
          )}

          {isSignedIn && !projectContext && (
            <nav className="hidden items-center gap-1 text-sm font-semibold text-slate-600 sm:flex">
              <Link className={navLinkClassName(pathname === "/dashboard")} href="/dashboard">
                Dashboard
              </Link>
              <Link
                className={navLinkClassName(pathname === "/projects/new")}
                href="/projects/new"
              >
                새 Project
              </Link>
            </nav>
          )}

          {isSignedIn && projectContext && (
            <div className="hidden min-w-0 items-center gap-3 sm:flex">
              <span aria-hidden className="text-slate-300">
                /
              </span>
              <Link
                className="rounded-lg px-2 py-1 text-sm font-bold text-cyan-700 transition hover:bg-cyan-50 hover:text-cyan-800"
                href="/dashboard"
              >
                Dashboard
              </Link>
              <nav className="flex items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-100 p-1 text-[13px] font-bold text-slate-500">
                {PROJECT_SECTIONS.map((section) => (
                  <Link
                    className={
                      projectContext.section === section.slug
                        ? "rounded-lg bg-white px-3 py-1.5 text-cyan-800 shadow-sm"
                        : "rounded-lg px-3 py-1.5 transition hover:text-cyan-700"
                    }
                    href={`/projects/${projectContext.projectId}/${section.slug}`}
                    key={section.slug}
                  >
                    {section.label}
                  </Link>
                ))}
              </nav>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isSignedIn && projectContext && (
            <span
              className="hidden max-w-[200px] items-center gap-2 text-[13px] font-bold text-slate-500 sm:inline-flex"
              title="현재 보고 있는 프로젝트"
            >
              <span
                aria-hidden
                className="h-2 w-2 shrink-0 rounded-full bg-emerald-500 ring-3 ring-emerald-100"
              />
              <span className="truncate">{projectName ?? "프로젝트"}</span>
            </span>
          )}
          {session.state === "signed-out" && (
            <div className="hidden items-center gap-2 sm:flex">
              <Link
                className="rounded-xl px-3.5 py-2 text-sm font-bold text-slate-600 transition hover:text-cyan-700"
                href="/login"
              >
                로그인
              </Link>
              <Link
                className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-cyan-700"
                href="/signup"
              >
                무료로 시작
              </Link>
            </div>
          )}

          {isSignedIn && (
            <div className="relative hidden sm:block" ref={userMenuRef}>
              <button
                aria-expanded={isUserMenuOpen}
                aria-haspopup="menu"
                aria-label="계정 메뉴"
                className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2 transition hover:border-cyan-400"
                onClick={() => setIsUserMenuOpen((open) => !open)}
                type="button"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-cyan-600 text-[13px] font-black text-white">
                  {avatarInitial}
                </span>
                <span aria-hidden className="text-xs text-slate-400">
                  ▾
                </span>
              </button>
              {isUserMenuOpen && (
                <div
                  className="absolute right-0 top-full z-50 mt-2 w-56 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10"
                  role="menu"
                >
                  <p className="border-b border-slate-100 px-3 pb-2 pt-1.5 text-xs text-slate-500">
                    로그인 계정
                    <span className="mt-0.5 block break-all text-[13px] font-bold text-slate-900">
                      {userEmail ?? "확인 중"}
                    </span>
                  </p>
                  <button
                    className="mt-1 w-full rounded-xl px-3 py-2 text-left text-sm font-bold text-rose-600 transition hover:bg-rose-50"
                    onClick={handleLogout}
                    role="menuitem"
                    type="button"
                  >
                    로그아웃
                  </button>
                </div>
              )}
            </div>
          )}

          {session.state !== "loading" && (
            <button
              aria-expanded={isMobileMenuOpen}
              aria-label={isMobileMenuOpen ? "메뉴 닫기" : "메뉴 열기"}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-cyan-400 hover:text-cyan-700 sm:hidden"
              onClick={() => setIsMobileMenuOpen((open) => !open)}
              type="button"
            >
              <svg aria-hidden className="h-4 w-4" fill="none" viewBox="0 0 16 16">
                {isMobileMenuOpen ? (
                  <path
                    d="M3 3l10 10M13 3L3 13"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeWidth="1.75"
                  />
                ) : (
                  <path
                    d="M2 4h12M2 8h12M2 12h12"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeWidth="1.75"
                  />
                )}
              </svg>
            </button>
          )}
        </div>
      </div>

      {isMobileMenuOpen && (
        <nav className="border-t border-slate-200 bg-white px-4 pb-4 pt-2 sm:hidden">
          {session.state === "signed-out" && (
            <div className="grid gap-1">
              {!hideGuestNav && (
                <>
                  <Link
                    className={mobileLinkClassName(false)}
                    href="/#flow"
                    onClick={closeMobileMenu}
                  >
                    사용 흐름
                  </Link>
                  <Link
                    className={mobileLinkClassName(false)}
                    href="/#features"
                    onClick={closeMobileMenu}
                  >
                    기능
                  </Link>
                  <a
                    className={mobileLinkClassName(false)}
                    href="https://github.com/Shin-H-S/AIM"
                    onClick={closeMobileMenu}
                    rel="noreferrer"
                    target="_blank"
                  >
                    GitHub
                  </a>
                </>
              )}
              <Link
                className={mobileLinkClassName(pathname === "/login")}
                href="/login"
                onClick={closeMobileMenu}
              >
                로그인
              </Link>
              <Link
                className="mt-1 rounded-xl bg-cyan-600 px-3 py-2.5 text-center text-sm font-bold text-white transition hover:bg-cyan-700"
                href="/signup"
                onClick={closeMobileMenu}
              >
                무료로 시작
              </Link>
            </div>
          )}

          {isSignedIn && (
            <div className="grid gap-1">
              <Link
                className={mobileLinkClassName(pathname === "/dashboard")}
                href="/dashboard"
                onClick={closeMobileMenu}
              >
                Dashboard
              </Link>
              <Link
                className={mobileLinkClassName(pathname === "/projects/new")}
                href="/projects/new"
                onClick={closeMobileMenu}
              >
                새 Project
              </Link>
              {projectContext && (
                <>
                  <p className="mt-2 truncate px-3 text-xs font-bold text-slate-400">
                    {projectName ?? "프로젝트"}
                  </p>
                  {PROJECT_SECTIONS.map((section) => (
                    <Link
                      className={mobileLinkClassName(projectContext.section === section.slug)}
                      href={`/projects/${projectContext.projectId}/${section.slug}`}
                      key={section.slug}
                      onClick={closeMobileMenu}
                    >
                      {section.label}
                    </Link>
                  ))}
                </>
              )}
              <p className="mt-2 break-all border-t border-slate-100 px-3 pt-2 text-xs text-slate-500">
                {userEmail ?? "로그인됨"}
              </p>
              <button
                className="rounded-xl px-3 py-2.5 text-left text-sm font-bold text-rose-600 transition hover:bg-rose-50"
                onClick={handleLogout}
                type="button"
              >
                로그아웃
              </button>
            </div>
          )}
        </nav>
      )}
    </header>
  );
}

function navLinkClassName(isActive: boolean) {
  return `rounded-xl px-3.5 py-2 transition ${
    isActive ? "bg-cyan-50 text-cyan-800" : "hover:bg-slate-100 hover:text-cyan-700"
  }`;
}

function mobileLinkClassName(isActive: boolean) {
  return `rounded-xl px-3 py-2.5 text-sm font-bold transition ${
    isActive ? "bg-cyan-50 text-cyan-800" : "text-slate-600 hover:bg-slate-100 hover:text-cyan-700"
  }`;
}
