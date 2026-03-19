import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Project Veracity — Hallucination Firewall',
  description: 'Real-time AI hallucination detection and auto-correction firewall',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}