import "./globals.css";
import type React from "react";

export const metadata = {
  title: "philosophia-engine",
  description: "Philosophy RAG + semantic search MVP"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

