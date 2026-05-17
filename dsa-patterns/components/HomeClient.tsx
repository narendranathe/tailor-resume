"use client";

import { useEffect, useMemo, useState } from "react";
import { patterns, totalPatterns, totalProblems, uniqueProblemCount } from "@/data/patterns";
import PatternCard from "@/components/PatternCard";
import { getAll, resetAll } from "@/lib/storage";

export default function HomeClient() {
  const [query, setQuery] = useState("");
  const [doneCount, setDoneCount] = useState(0);

  useEffect(() => {
    const update = () => setDoneCount(Object.keys(getAll()).length);
    update();
    window.addEventListener("dsa-progress-changed", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("dsa-progress-changed", update);
      window.removeEventListener("storage", update);
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return patterns;
    return patterns.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.short.toLowerCase().includes(q) ||
        p.problems.some((pr) => pr.title.toLowerCase().includes(q))
    );
  }, [query]);

  const pct = totalProblems === 0 ? 0 : Math.round((doneCount / totalProblems) * 100);

  return (
    <>
      <section className="mb-8">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-gradient-to-br from-brand-50 to-white dark:from-slate-900 dark:to-slate-950 p-6 sm:p-8">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Master <span className="text-brand-600">DSA Patterns</span>
          </h1>
          <p className="mt-3 max-w-2xl text-slate-600 dark:text-slate-300">
            {totalPatterns} essential patterns. {uniqueProblemCount} unique LeetCode problems
            ({totalProblems} slots — some show up under more than one pattern).
            Solve, check off, and watch your progress grow.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-semibold tabular-nums">{doneCount}</span>
              <span className="text-slate-500 dark:text-slate-400">/ {totalProblems} solved</span>
            </div>
            <div className="h-2 w-48 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
              <div className="h-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-sm tabular-nums text-slate-500 dark:text-slate-400">{pct}%</span>
            {doneCount > 0 && (
              <button
                className="btn-ghost text-xs"
                onClick={() => {
                  if (confirm("Reset all progress? This cannot be undone.")) resetAll();
                }}
              >
                Reset progress
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="mb-6 flex items-center gap-3">
        <div className="relative flex-1">
          <input
            type="search"
            placeholder="Search patterns or problems..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 pl-10 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-200 dark:focus:ring-brand-800"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔎</span>
        </div>
      </section>

      <section>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((p) => (
            <PatternCard key={p.slug} pattern={p} />
          ))}
        </div>
        {filtered.length === 0 && (
          <p className="text-center text-slate-500 dark:text-slate-400 py-12">
            No patterns match &quot;{query}&quot;.
          </p>
        )}
      </section>
    </>
  );
}
