"use client";

import dynamic from "next/dynamic";

/**
 * Lazy-loaded wrapper around EpisodeCharts (~110 KB of recharts).
 * Defers the chart bundle until the user actually opens Browse or Annotate
 * so the initial route stays slim.
 */
export const EpisodeCharts = dynamic(
  () => import("./episode-charts").then((mod) => mod.EpisodeCharts),
  {
    ssr: false,
    loading: () => (
      <div className="episode-charts episode-charts-empty">
        <span className="muted">Loading charts…</span>
      </div>
    )
  }
);
