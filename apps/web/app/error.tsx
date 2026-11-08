"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Do not log document content or tokens to the browser console.
    console.error("Sigillum interface error", { digest: error.digest });
  }, [error]);

  return (
    <main className="page-stack narrow-page">
      <div className="eyebrow">WORKSPACE ERROR</div>
      <h1>This view could not be loaded.</h1>
      <p className="subhead">Your saved submissions and original files have not been changed by this interface error.</p>
      <div className="alert error">{error.message || "An unexpected interface error occurred."}</div>
      <button className="button secondary" onClick={() => reset()}>Try again</button>
    </main>
  );
}
