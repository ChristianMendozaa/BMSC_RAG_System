import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Bank Documentation Chat",
  description: "Internal document search and chat for bank employees",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-gray-50">
        <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6 shrink-0">
          <span className="font-semibold text-gray-900 text-sm tracking-tight">
            📄 DocChat Bancario
          </span>
          <div className="flex gap-1">
            <Link
              href="/chat"
              className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              Chat
            </Link>
            <Link
              href="/documents"
              className="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              Documentos
            </Link>
          </div>
        </nav>
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}
