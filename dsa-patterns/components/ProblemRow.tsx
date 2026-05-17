"use client";

import { useEffect, useState } from "react";
import { getDone, setDone } from "@/lib/storage";
import { leetcodeUrl, type Problem } from "@/data/patterns";

type Props = {
  problem: Problem;
  patternSlug: string;
  patternName?: string;
  showPattern?: boolean;
};

const diffClass: Record<Problem["difficulty"], string> = {
  Easy: "diff-easy",
  Medium: "diff-medium",
  Hard: "diff-hard",
};

export default function ProblemRow({ problem, patternSlug, patternName, showPattern }: Props) {
  const [done, setLocal] = useState(false);

  useEffect(() => {
    setLocal(getDone(patternSlug, problem.id));
    const onChange = () => setLocal(getDone(patternSlug, problem.id));
    window.addEventListener("dsa-progress-changed", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("dsa-progress-changed", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, [patternSlug, problem.id]);

  const toggle = () => {
    const next = !done;
    setLocal(next);
    setDone(patternSlug, problem.id, next);
  };

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-slate-50 dark:hover:bg-slate-800/60">
      <input
        type="checkbox"
        checked={done}
        onChange={toggle}
        aria-label={`Mark ${problem.title} as solved`}
        className="h-4 w-4 rounded border-slate-300 dark:border-slate-600 accent-brand-600"
      />
      <span className="font-mono text-xs text-slate-500 dark:text-slate-400 w-12 shrink-0 tabular-nums">
        #{problem.id}
      </span>
      <a
        href={leetcodeUrl(problem.slug)}
        target="_blank"
        rel="noreferrer"
        className={`flex-1 truncate ${done ? "line-through text-slate-400 dark:text-slate-500" : "hover:text-brand-600 dark:hover:text-brand-400"}`}
      >
        {problem.title}
        {problem.premium && (
          <span className="ml-2 chip bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            premium
          </span>
        )}
      </a>
      {showPattern && patternName && (
        <span className="hidden sm:inline chip bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
          {patternName}
        </span>
      )}
      <span className={`chip ${diffClass[problem.difficulty]}`}>{problem.difficulty}</span>
    </div>
  );
}
