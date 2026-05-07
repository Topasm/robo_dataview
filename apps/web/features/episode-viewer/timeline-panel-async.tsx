"use client";

import dynamic from "next/dynamic";

/**
 * Lazy-loaded wrapper around TimelinePanel (~448 LOC plus clip-validation
 * helpers). The timeline only appears in Annotate mode; loading the bundle
 * on demand keeps Browse-only sessions from paying for it.
 */
export const TimelinePanel = dynamic(
  () =>
    import("./timeline-panel").then((mod) => mod.TimelinePanel),
  {
    ssr: false,
    loading: () => (
      <section className="timeline-panel timeline-panel--loading">
        <span className="muted">Loading timeline…</span>
      </section>
    )
  }
);
