import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";
import { AuthProvider } from "@/lib/auth-context";
import { ChatStreamProvider } from "@/lib/chat-stream-context";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Asistente Mercantil | Banco Mercantil Santa Cruz",
  description: "Consultas internas sobre documentación del Banco Mercantil Santa Cruz",
  icons: {
    icon: "/LogoBMSC.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full flex flex-col" style={{ background: 'var(--bg-base)' }}>
        <AuthProvider>
          <ChatStreamProvider>
            <NavBar />
            <main className="flex-1 flex flex-col overflow-hidden">{children}</main>
          </ChatStreamProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
