"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Pattern, Difficulty } from "@/data/patterns";
import ProblemRow from "@/components/ProblemRow";
import { countDoneForPattern } from "@/lib/storage";

type Filter = "All" | Difficulty | "Todo" | "Done";

const filterOptions: Filter[] = ["All", "Easy", "Medium", "Hard", "Todo", "Done"];

export default function PatternDetailClient({ pattern }: { pattern: Pattern }) {
  const [filter, setFilter] = useState<Filter>("All");
  const [query, setQuery] = useState("");
  const [done, setDone] = useState(0);

  useEffect(() => {
    const update = () =>
      setDone(countDoneForPattern(pattern.slug, pattern.problems.map((p) => p.id)));
    update();
    window.addEventListener("dsa-progress-changed", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("dsa-progress-changed", update);
      window.removeEventListener("storage", update);
    };
  }, [pattern.slug, pattern.problems]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return pattern.problems.filter((p) => {
      if (q && !p.title.toLowerCase().includes(q) && !String(p.id).includes(q)) return false;
      if (filter === "Easy" || filter === "Medium" || filter === "Hard") return p.difficulty === filter;
      return true;
    });
  }, [pattern.problems, query, filter]);

  // Done/Todo filter needs live store check — re-render keyed by `done` count covers it
  const finalList = useMemo(() => {
    if (filter !== "Done" && filter !== "Todo") return filtered;
    return filtered.filter((p) => {
      const isDone = countDoneForPattern(pattern.slug, [p.id]) === 1;
      return filter === "Done" ? isDone : !isDone;
    });
  }, [filtered, filter, pattern.slug, done]);

  const total = pattern.problems.length;
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);

  return (
    <article>
      <nav className="text-sm text-slate-500 dark:text-slate-400 mb-4">
        <Link href="/" className="hover:text-brand-600">← All patterns</Link>
      </nav>

      <header className="card p-6 mb-6">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-lg bg-brand-50 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 flex items-center justify-center text-xl font-bold">
            {pattern.emoji}
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold tracking-tight">{pattern.name}</h1>
            <p className="mt-1 text-slate-600 dark:text-slate-300">{pattern.short}</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums">{done}/{total}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">{pct}% solved</div>
          </div>
        </div>
        <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div className="h-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="card p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            What it is
          </h2>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
            {pattern.description}
          </p>
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            When to use
          </h2>
          <ul className="text-sm text-slate-700 dark:text-slate-300 list-disc pl-5 space-y-1">
            {pattern.whenToUse.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mt-4 mb-2">
            Key ideas
          </h3>
          <ul className="text-sm text-slate-700 dark:text-slate-300 list-disc pl-5 space-y-1">
            {pattern.keyIdeas.map((k) => (
              <li key={k}>{k}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card p-2 sm:p-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-2 sm:px-1 mb-2">
          <h2 className="text-lg font-semibold flex-1">Problems</h2>
          <input
            type="search"
            placeholder="Filter by title or #"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full sm:w-64 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm outline-none focus:border-brand-500"
          />
        </div>
        <div className="flex flex-wrap gap-1 px-2 sm:px-1 mb-2">
          {filterOptions.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`chip cursor-pointer ${
                filter === f
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {finalList.map((p) => (
            <ProblemRow key={p.id} problem={p} patternSlug={pattern.slug} />
          ))}
          {finalList.length === 0 && (
            <p className="text-center text-sm text-slate-500 dark:text-slate-400 py-8">
              No problems match this filter.
            </p>
          )}
        </div>
      </section>
    </article>
  );
}
