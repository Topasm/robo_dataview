import { useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";

import type { SearchResult } from "@/lib/types";

type SearchFilterBarProps = {
  results: SearchResult[];
  onFilterSearch: (query: string) => Promise<void>;
  onSelectResult: (episodeIndex: number) => void;
  onSemanticSearch: (text: string) => Promise<void>;
};

export function SearchFilterBar({
  onFilterSearch,
  results,
  onSelectResult,
  onSemanticSearch
}: SearchFilterBarProps) {
  const [query, setQuery] = useState("cloth edge grasp");
  const [isSearching, setIsSearching] = useState(false);

  async function handleSearch() {
    if (!query.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      await onSemanticSearch(query.trim());
    } finally {
      setIsSearching(false);
    }
  }

  async function handleFilter() {
    if (!query.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      await onFilterSearch(query.trim());
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <section className="search-filter-bar">
      <div className="search-box">
        <Search size={16} />
        <input onChange={(event) => setQuery(event.target.value)} value={query} />
      </div>
      <button
        className="icon-button"
        disabled={isSearching}
        onClick={handleSearch}
        title="Semantic search"
        type="button"
      >
        <Search size={16} />
      </button>
      <button
        className="icon-button"
        disabled={isSearching}
        onClick={handleFilter}
        title="Episode filter"
        type="button"
      >
        <SlidersHorizontal size={16} />
      </button>
      {results.length > 0 ? (
        <div className="search-results">
          {results.map((result) => (
            <button
              className="search-result"
              key={`${result.episodeIndex}-${result.frameIndex ?? "episode"}-${result.label}`}
              onClick={() => onSelectResult(result.episodeIndex)}
              type="button"
            >
              <span className="mono">#{result.episodeIndex}</span>
              <span>{result.label}</span>
              <span>{result.score?.toFixed(2) ?? ""}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
