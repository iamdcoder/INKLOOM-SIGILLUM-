export default function Loading() {
  return (
    <div className="loading-panel" role="status" aria-live="polite">
      <div className="spinner" />
      Loading workspace…
    </div>
  );
}
