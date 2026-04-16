import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TK101 AI Platform",
  description: "사내 40명 대상 AI 업무 자동화 플랫폼",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
