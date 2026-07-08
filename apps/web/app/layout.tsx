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
    <html className="scroll-smooth" lang="ko">
      <body className="min-h-screen bg-slate-100 text-slate-900">
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
