import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "恋爱模拟器 Phase 2",
  description: "多 Agent scene runtime、timeline replay 和 relationship cards 的恋综模拟器。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
