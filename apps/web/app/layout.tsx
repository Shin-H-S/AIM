import type { Metadata } from "next";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIM",
  description: "AI-powered web service quality assessment and monitoring platform",
  other: {
    // AIM이 AIM 자신을 모니터링하기 위한 도메인 소유권 검증 태그 (dogfooding)
    "aim-verification": "aim_verify_Xi_8qytEY4nOmPZ2VOoRaf7_ptWBc-Bo"
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className="scroll-smooth" lang="ko" suppressHydrationWarning>
      <body className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        {/* 첫 페인트 전에 저장된 테마(없으면 시스템 설정)를 적용해 깜빡임을 막는다. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              '(function(){try{var t=localStorage.getItem("aim-theme");if(t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches)){document.documentElement.classList.add("dark");}}catch(e){}})();'
          }}
        />
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
