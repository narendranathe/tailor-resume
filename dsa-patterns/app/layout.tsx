import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import ThemeToggle from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "DSA Patterns — Master Coding Interviews",
  description:
    "Practice 20+ DSA patterns with 250+ curated LeetCode problems. Track your progress, search across patterns, and master coding interviews.",
};

const themeInitScript = `
  (function() {
    try {
      var t = localStorage.getItem('theme');
      if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
      }
    } catch (e) {}
  })();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <header className="sticky top-0 z-40 border-b border-slate-200 dark:border-slate-800 bg-white/85 dark:bg-slate-950/85 backdrop-blur">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-bold text-lg">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">DS</span>
              <span>DSA Patterns</span>
            </Link>
            <nav className="flex items-center gap-1 sm:gap-3 text-sm">
              <Link href="/" className="btn-ghost">Patterns</Link>
              <Link href="/problems" className="btn-ghost">All Problems</Link>
              <a href="https://leetcode.com/" target="_blank" rel="noreferrer" className="btn-ghost hidden sm:inline-flex">LeetCode ↗</a>
              <ThemeToggle />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 sm:px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 sm:px-6 py-10 text-sm text-slate-500 dark:text-slate-400 border-t border-slate-200 dark:border-slate-800 mt-16">
          <p>
            Curated patterns inspired by Grokking the Coding Interview, NeetCode 150, Blind 75, and AlgoMaster.
            Problem links go directly to LeetCode. Progress is saved locally in your browser.
          </p>
        </footer>
      </body>
    </html>
  );
}
