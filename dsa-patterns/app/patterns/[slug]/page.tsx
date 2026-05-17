import { notFound } from "next/navigation";
import { patterns, findPattern } from "@/data/patterns";
import PatternDetailClient from "@/components/PatternDetailClient";
import type { Metadata } from "next";

export function generateStaticParams() {
  return patterns.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const p = findPattern(slug);
  if (!p) return { title: "Pattern not found" };
  return {
    title: `${p.name} — DSA Patterns`,
    description: p.short,
  };
}

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const pattern = findPattern(slug);
  if (!pattern) notFound();
  return <PatternDetailClient pattern={pattern} />;
}
