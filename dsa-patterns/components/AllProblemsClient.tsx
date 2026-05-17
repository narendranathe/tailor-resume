"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { allProblems, patterns, type Difficulty } from "@/data/patterns";
import ProblemRow from "@/components/ProblemRow";
import { getAll } from "@/lib/storage";

type DiffFilter = "All" | Difficulty;
type StatusFilter = "All" | "Todo" | "Done";

export default function AllProblemsClient() {
  const [query, setQuery] = useState("");
  const [diff, setDiff] = useState<DiffFilter>("All");
  const [status, setStatus] = useState<StatusFilter>("All");
  const [patternSlug, setPatternSlug] = useState<string>("All");
  const [doneTick, setDoneTick] = useState(0);

  useEffect(() => {
    const onChange = () => setDoneTick((t) => t + 1);
    window.addEventListener("dsa-progress-changed", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("dsa-progress-changed", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const store = getAll();
    return allProblems.filter((p) => {
      if (q && !p.title.toLowerCase().includes(q) && !String(p.id).includes(q)) return false;
      if (diff !== "All" && p.difficulty !== diff) return false;
      if (patternSlug !== "All" && p.patternSlug !== patternSlug) return false;
      if (status !== "All") {
        const isDone = !!store[`${p.patternSlug}:${p.id}`];
        if (status === "Done" && !isDone) return false;
        if (status === "Todo" && isDone) return false;
      }
      return true;
    });
  }, [query, diff, status, patternSlug, doneTick]);

  return (
    <div>
      <nav className="text-sm text-slate-500 dark:text-slate-400 mb-4">
        <Link href="/" className="hover:text-brand-600">← All patterns</Link>
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">All problems</h1>
        <p className="text-slate-600 dark:text-slate-300 mt-1">
          {allProblems.length} problem slots across {patterns.length} patterns
          {" — drawn from the AlgoMaster 300, Blind 75, NeetCode 150, and Top Interview 150."}
        </p>
      </header>

      <section className="card p-4 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <input
            type="search"
            placeholder="Search by title or #"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="sm:col-span-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <select
            value={patternSlug}
            onChange={(e) => setPatternSlug(e.target.value)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm outline-none focus:border-brand-500"
          >
            <option value="All">All patterns</option>
            {patterns.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name}</option>
            ))}
          </select>
          <select
            value={diff}
            onChange={(e) => setDiff(e.target.value as DiffFilter)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm outline-none focus:border-brand-500"
          >
            <option value="All">All difficulties</option>
            <option value="Easy">Easy</option>
            <option value="Medium">Medium</option>
            <option value="Hard">Hard</option>
          </select>
        </div>
        <div className="flex gap-1 mt-3">
          {(["All", "Todo", "Done"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`chip cursor-pointer ${
                status === s
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              {s}
            </button>
          ))}
          <span className="ml-auto text-xs text-slate-500 dark:text-slate-400 self-center">
            {filtered.length} shown
          </span>
        </div>
      </section>

      <section className="card p-2 sm:p-4">
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {filtered.map((p) => (
            <ProblemRow
              key={`${p.patternSlug}-${p.id}`}
              problem={p}
              patternSlug={p.patternSlug}
              patternName={p.patternName}
              showPattern
            />
          ))}
          {filtered.length === 0 && (
            <p className="text-center text-sm text-slate-500 dark:text-slate-400 py-8">
              No problems match these filters.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
