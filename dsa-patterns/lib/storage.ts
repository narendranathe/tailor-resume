"use client";

const KEY = "dsa-progress-v1";

type Store = Record<string, boolean>;

function read(): Store {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function write(store: Store) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY, JSON.stringify(store));
    window.dispatchEvent(new CustomEvent("dsa-progress-changed"));
  } catch {}
}

export function problemKey(patternSlug: string, problemId: number) {
  return `${patternSlug}:${problemId}`;
}

export function getDone(patternSlug: string, problemId: number): boolean {
  return !!read()[problemKey(patternSlug, problemId)];
}

export function setDone(patternSlug: string, problemId: number, done: boolean) {
  const store = read();
  const k = problemKey(patternSlug, problemId);
  if (done) store[k] = true;
  else delete store[k];
  write(store);
}

export function getAll(): Store {
  return read();
}

export function countDoneForPattern(patternSlug: string, problemIds: number[]): number {
  const store = read();
  let n = 0;
  for (const id of problemIds) if (store[problemKey(patternSlug, id)]) n++;
  return n;
}

export function resetAll() {
  write({});
}
