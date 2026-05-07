"use client";

import dynamic from "next/dynamic";

/**
 * Lazy-loaded wrapper around SearchFilterBar (~484 LOC of search/filter UI).
 * Only the Annotate IconRail ever renders this, and only when the user
 * actually opens the search panel — so deferring the chunk keeps the initial
 * route lean.
 */
export const SearchFilterBar = dynamic(
  () =>
    import("./search-filter-bar").then((mod) => mod.SearchFilterBar),
  {
    ssr: false,
    loading: () => (
      <section className="search-filter-bar">
        <span className="muted">Loading search…</span>
      </section>
    )
  }
);
