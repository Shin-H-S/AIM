import type { Metadata } from "next";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIM",
  description: "AI-powered web service quality assessment and monitoring platform"
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
