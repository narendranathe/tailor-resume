# DSA Patterns

A practice site for mastering Data Structures & Algorithms by pattern.
20 essential patterns, ~260 curated LeetCode problems, progress tracked locally in your browser.

Inspired by AlgoMaster, Grokking the Coding Interview, NeetCode 150, and Blind 75.

## Stack

- Next.js 15 (App Router, static export)
- React 19
- TypeScript
- Tailwind CSS 3

## Develop

```bash
npm install
npm run dev          # http://localhost:3000
```

## Build (static export)

```bash
npm run build
# Output in ./out — deploy to any static host (Vercel, Netlify, GitHub Pages, S3, ...)
```

## Project structure

```
app/
  layout.tsx
  page.tsx                     # home (pattern grid)
  patterns/[slug]/page.tsx     # pattern detail with problems
  problems/page.tsx            # all problems with filters
components/
  HomeClient.tsx
  PatternCard.tsx
  PatternDetailClient.tsx
  AllProblemsClient.tsx
  ProblemRow.tsx
  ThemeToggle.tsx
data/
  patterns.ts                  # patterns + problem catalog (single source of truth)
lib/
  storage.ts                   # localStorage-based progress
```

## Adding patterns or problems

Edit `data/patterns.ts`. Each problem is `{ id, title, slug, difficulty, premium? }`.
`slug` is the LeetCode URL slug — links are generated as `leetcode.com/problems/<slug>/`.

## Deploy

`output: "export"` is set in `next.config.ts`, so `npm run build` produces a fully static
site in `./out`. Drop it on Vercel, Netlify, Cloudflare Pages, or GitHub Pages.

## License

MIT.
