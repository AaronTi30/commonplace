import "./globals.css";
import type React from "react";
import { Inter } from "next/font/google";
import { Providers } from "@/components/providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata = {
  title: "commonplace",
  description: "Philosophy RAG + semantic search MVP"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen bg-zinc-50 text-zinc-900 antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
