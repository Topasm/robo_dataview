import { Search, SlidersHorizontal } from "lucide-react";

export function SearchFilterBar() {
  return (
    <section className="search-filter-bar">
      <div className="search-box">
        <Search size={16} />
        <input defaultValue='success_label = true AND quality_score > 0.8' />
      </div>
      <button className="icon-button" title="Filter builder" type="button">
        <SlidersHorizontal size={16} />
      </button>
    </section>
  );
}
