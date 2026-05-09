"use client";

import { Download, Film, HelpCircle, Pin, PinOff, Search, Sparkles } from "lucide-react";

import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { RerunPanel } from "@/features/rerun-viewer/rerun-panel";
import { SearchFilterBar } from "@/features/search-filter/search-filter-bar-async";
import type { IconRailPanel } from "@/lib/use-annotation-editor";
import type { useStudioData } from "@/lib/use-studio-data";

type StudioData = ReturnType<typeof useStudioData>;

type IconRailProps = {
  studio: StudioData;
  activePanel: IconRailPanel;
  pinned: boolean;
  onTogglePanel: (panel: IconRailPanel) => void;
  onTogglePin: () => void;
  onOpenCheatsheet: () => void;
  exportModalOpen: boolean;
  onToggleExport: () => void;
};

export function IconRail({
  studio,
  activePanel,
  pinned,
  onTogglePanel,
  onTogglePin,
  onOpenCheatsheet,
  exportModalOpen,
  onToggleExport
}: IconRailProps) {
  return (
    <aside className={`icon-rail-shell${activePanel ? " expanded" : ""}`}>
      <nav className="icon-rail" aria-label="Annotation tools">
        <button
          type="button"
          className={`icon-rail-button${activePanel === "episodes" ? " active" : ""}`}
          onClick={() => onTogglePanel("episodes")}
          title="Episodes (E) — toggle the episode list"
          aria-label="Toggle episode list"
          aria-pressed={activePanel === "episodes"}
        >
          <Film size={18} />
          <span className="icon-rail-badge">{studio.episodeRows.length}</span>
        </button>
        <button
          type="button"
          className={`icon-rail-button${activePanel === "search" ? " active" : ""}`}
          onClick={() => onTogglePanel("search")}
          title="Search & filter episodes"
          aria-label="Toggle search and filter panel"
          aria-pressed={activePanel === "search"}
        >
          <Search size={18} />
        </button>
        <button
          type="button"
          className={`icon-rail-button${activePanel === "rerun" ? " active" : ""}`}
          onClick={() => onTogglePanel("rerun")}
          title="Rerun (R) — open the 3D viewer panel"
          aria-label="Toggle Rerun viewer panel"
          aria-pressed={activePanel === "rerun"}
        >
          <Sparkles size={18} />
        </button>
        <span className="icon-rail-spacer" />
        <button
          type="button"
          className={`icon-rail-button${exportModalOpen ? " active" : ""}`}
          onClick={onToggleExport}
          title="Apply curated annotations to a new dataset version"
          aria-label="Open the apply-to-dataset panel"
          aria-pressed={exportModalOpen}
        >
          <Download size={18} />
        </button>
        <button
          type="button"
          className="icon-rail-button"
          onClick={onOpenCheatsheet}
          title="Keyboard shortcuts (?)"
          aria-label="Open keyboard shortcuts"
        >
          <HelpCircle size={18} />
        </button>
      </nav>
      {activePanel ? (
        <section className="icon-rail-popout" role="region" aria-label={panelTitle(activePanel)}>
          <header className="icon-rail-popout-header">
            <span>{panelTitle(activePanel)}</span>
            <button
              type="button"
              className="btn btn--ghost btn--icon btn--sm"
              onClick={onTogglePin}
              title={pinned ? "Unpin panel — auto-collapses on focus loss" : "Pin panel open"}
              aria-label={pinned ? "Unpin panel" : "Pin panel"}
              aria-pressed={pinned}
            >
              {pinned ? <PinOff size={14} /> : <Pin size={14} />}
            </button>
          </header>
          <div className="icon-rail-popout-body">
            {activePanel === "episodes" ? (
              <EpisodeList
                compact
                episodes={studio.episodeRows}
                onSelectEpisode={studio.handleSelectEpisode}
                selectedEpisodeIndex={studio.selectedEpisodeIndex}
              />
            ) : null}
            {activePanel === "search" ? (
              <SearchFilterBar
                filterPresets={studio.filterPresets}
                onCreateFilterPreset={studio.handleCreateFilterPreset}
                onDeleteFilterPreset={studio.handleDeleteFilterPreset}
                onFilterSearch={studio.handleFilterSearch}
                onSelectResult={studio.handleSelectEpisode}
                onSemanticSearch={studio.handleSemanticSearch}
                results={studio.searchResults}
              />
            ) : null}
            {activePanel === "rerun" ? (
              <RerunPanel
                job={studio.rerunJob}
                onCreateSession={studio.handleCreateRerunSession}
                session={studio.rerunSession}
                viewerUrl={studio.rerunViewerUrl}
              />
            ) : null}
          </div>
        </section>
      ) : null}
    </aside>
  );
}

function panelTitle(panel: NonNullable<IconRailPanel>): string {
  if (panel === "episodes") {
    return "Episodes";
  }
  if (panel === "search") {
    return "Search";
  }
  return "Rerun";
}
