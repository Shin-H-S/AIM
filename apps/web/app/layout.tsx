import type { Metadata } from "next";
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
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
