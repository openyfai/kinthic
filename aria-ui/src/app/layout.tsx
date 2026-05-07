import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ARIA Web Interface",
  description: "Advanced Sovereign AGI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="dark h-full antialiased font-sans"
    >
      <body className="min-h-full flex flex-col bg-primary text-primary-foreground font-sans">{children}</body>
    </html>
  );
}
