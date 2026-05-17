import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-3xl font-bold">404</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-300">Pattern or page not found.</p>
      <Link href="/" className="btn-primary mt-6">Back to patterns</Link>
    </div>
  );
}
