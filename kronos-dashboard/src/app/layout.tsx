import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Kronos Studio',
  description: 'Epistemic Graph and Control Center for Kronos AGI',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-[#0A0A0F] text-white overflow-hidden h-screen w-screen selection:bg-[#F5A623]/30`}>
        <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#1A1A2E]/80 via-[#0A0A0F] to-[#050508] -z-10" />
        {children}
      </body>
    </html>
  );
}
