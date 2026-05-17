"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Pattern } from "@/data/patterns";
import { countDoneForPattern } from "@/lib/storage";

export default function PatternCard({ pattern }: { pattern: Pattern }) {
  const [done, setDone] = useState(0);
  const total = pattern.problems.length;

  useEffect(() => {
    const update = () =>
      setDone(countDoneForPattern(pattern.slug, pattern.problems.map((p) => p.id)));
    update();
    const onChange = () => update();
    window.addEventListener("dsa-progress-changed", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("dsa-progress-changed", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, [pattern.slug, pattern.problems]);

  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const easy = pattern.problems.filter((p) => p.difficulty === "Easy").length;
  const med = pattern.problems.filter((p) => p.difficulty === "Medium").length;
  const hard = pattern.problems.filter((p) => p.difficulty === "Hard").length;

  return (
    <Link href={`/patterns/${pattern.slug}`} className="card card-hover p-5 block">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-brand-50 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 flex items-center justify-center text-lg font-bold">
            {pattern.emoji}
          </div>
          <div>
            <h3 className="font-semibold leading-tight">{pattern.name}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">{total} problems</p>
          </div>
        </div>
        <span className="chip bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
          {done}/{total}
        </span>
      </div>

      <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 line-clamp-2">{pattern.short}</p>

      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className="h-full rounded-full bg-brand-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs">
        <span className="chip diff-easy">E {easy}</span>
        <span className="chip diff-medium">M {med}</span>
        <span className="chip diff-hard">H {hard}</span>
      </div>
    </Link>
  );
}
