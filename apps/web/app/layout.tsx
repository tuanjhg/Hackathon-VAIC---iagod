import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ChatWidget } from "@/components/ChatWidget";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = { title: "NeedWise Copilot", description: "Tư vấn máy lạnh theo nhu cầu thật" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="vi"><body><Providers><Header/><main className="min-h-[70vh]">{children}</main><Footer/><ChatWidget/></Providers></body></html>; }

