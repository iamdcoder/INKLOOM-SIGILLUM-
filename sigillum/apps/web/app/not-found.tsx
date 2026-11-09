import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page-stack narrow-page">
      <div className="eyebrow">404 · RECORD NOT FOUND</div>
      <h1>This record is unavailable.</h1>
      <p className="subhead">It may have been removed, may not exist, or your role may not have access to it.</p>
      <Link href="/" className="button secondary">Return to overview</Link>
    </main>
  );
}
