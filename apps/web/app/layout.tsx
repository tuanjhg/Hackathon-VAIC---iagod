import type { Metadata } from "next";
import "./globals.css";
import { fontBody, fontHeading } from "@/lib/fonts";
import { Header } from "@/components/Header";
import { TopBar } from "@/components/home/TopBar";
import { Footer } from "@/components/Footer";
import { ChatWidget } from "@/components/ChatWidget";
import { Providers } from "@/components/Providers";
import { themeInitScript } from "@/components/theme/ThemeProvider";

export const metadata: Metadata = {
  title: {
    default: "NeedWise Copilot — Tư vấn máy lạnh theo nhu cầu thật",
    template: "%s · NeedWise Copilot",
  },
  description:
    "So sánh và chọn máy lạnh phù hợp với diện tích, ngân sách và ưu tiên của bạn. Tư vấn minh bạch dựa trên catalog thật.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" suppressHydrationWarning className={`${fontHeading.variable} ${fontBody.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="font-sans">
        <Providers>
          <TopBar />
          <Header />
          <main className="min-h-[70vh]">{children}</main>
          <Footer />
          <ChatWidget />
        </Providers>
      </body>
    </html>
  );
}
