import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "GEO · AI visibility for local businesses",
  description: "See how often ChatGPT, Gemini and Perplexity recommend your business, and what to do about it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm text-white">G</span>
              GEO
              <span className="hidden text-sm font-normal text-muted sm:inline">AI visibility</span>
            </Link>
            <Link href="/new" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90">
              Add business
            </Link>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
      </body>
    </html>
  );
}
