import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ardee RAG Chatbot",
  description: "Authenticated RAG chatbot dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
