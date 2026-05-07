"use client";

import { Film, HelpCircle, Pin, PinOff, Search, Sparkles } from "lucide-react";

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
};

export function IconRail({
  studio,
  activePanel,
  pinned,
  onTogglePanel,
  onTogglePin,
  onOpenCheatsheet
}: IconRailProps) {
  return (
    <aside className={`icon-rail-shell${activePanel ? " expanded" : ""}`}>
      <nav className="icon-rail" aria-label="Annotation tools">
        <button
          type="button"
          className={`icon-rail-button${activePanel === "episodes" ? " active" : ""}`}
          onClick={() => onTogglePanel("episodes")}
          title="Episodes (E)"
          aria-pressed={activePanel === "episodes"}
        >
          <Film size={18} />
          <span className="icon-rail-badge">{studio.episodeRows.length}</span>
        </button>
        <button
          type="button"
          className={`icon-rail-button${activePanel === "search" ? " active" : ""}`}
          onClick={() => onTogglePanel("search")}
          title="Search & filter"
          aria-pressed={activePanel === "search"}
        >
          <Search size={18} />
        </button>
        <button
          type="button"
          className={`icon-rail-button${activePanel === "rerun" ? " active" : ""}`}
          onClick={() => onTogglePanel("rerun")}
          title="Rerun (R)"
          aria-pressed={activePanel === "rerun"}
        >
          <Sparkles size={18} />
        </button>
        <span className="icon-rail-spacer" />
        <button
          type="button"
          className="icon-rail-button"
          onClick={onOpenCheatsheet}
          title="Keyboard shortcuts (?)"
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
              title={pinned ? "Unpin panel" : "Pin panel"}
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
                onFullTextSearch={studio.handleFullTextSearch}
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
