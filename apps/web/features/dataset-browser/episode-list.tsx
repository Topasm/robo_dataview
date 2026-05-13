"use client";

import { useEffect, useState } from "react";
import {
  ArrowDownUp,
  Bot,
  Camera,
  Check,
  ChevronsDown,
  Flag,
  Loader2,
  MessageSquareText,
  RotateCcw,
  Search,
  Trash2,
  UserCheck,
  X
} from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { Episode, EpisodeDisposition, EpisodeMetadataFilters } from "@/lib/types";

type EpisodeListProps = {
  episodes: Episode[];
  selectedEpisodeIndex: number;
  onSelectEpisode: (episodeIndex: number) => void;
  /**
   * Per-row disposition handler. When provided, each row gets inline
   * Flag (with memo) and Delete (toggles to Undo when already deleted)
   * buttons. Annotate's compact list leaves it undefined to keep that
   * surface read-only.
   *
   * `kind = null` clears the disposition entirely (undo) — there is no
   * explicit "kept" action because untouched is the default.
   */
  onMarkDisposition?: (
    episodeIndex: number,
    kind: "deleted" | "flagged" | null,
    reason: string | null
  ) => void;
  episodeTotal?: number;
  hasMoreEpisodes?: boolean;
  isLoadingMore?: boolean;
  onLoadMoreEpisodes?: () => void;
  metadataFilters?: EpisodeMetadataFilters;
  isFilteringEpisodes?: boolean;
  onMetadataFiltersChange?: (filters: EpisodeMetadataFilters) => void;
  searchText?: string;
  onSearchTextChange?: (text: string) => void | Promise<void>;
  compact?: boolean;
};

type QuickFilter = "all" | "new" | "no_label" | "failure" | "auto";
type SortKey = "episode_index" | "quality" | "status";
type DispositionFilter = "all" | EpisodeDisposition;

// "new" mirrors the StatusPill label for `reviewStatus === "pending"` so
// the dropdown reads the same as the in-row pill. The legacy "Bad/Drop"
// filter (reviewStatus === "rejected") was dropped because it overlapped
// with the Deleted disposition filter — both ended up surfacing the same
// "this episode is being thrown away" intent.
const QUICK_FILTERS: { key: QuickFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "no_label", label: "No Label" },
  { key: "failure", label: "Failure" },
  { key: "auto", label: "Auto Labels" }
];

const DISPOSITION_FILTERS: { key: DispositionFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "deleted", label: "Deleted" },
  { key: "flagged", label: "Flagged" }
];

const DEFAULT_METADATA_FILTERS: EpisodeMetadataFilters = {
  instruction: "all",
  wristCamera: "all"
};

const DISPOSITION_BADGE_LABEL: Record<EpisodeDisposition, string> = {
  deleted: "Deleted",
  flagged: "Flagged"
};

function matchFilter(episode: Episode, filter: QuickFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "new":
      return episode.reviewStatus === "pending";
    case "no_label":
      return !episode.hasHumanLabel && !episode.hasVlmLabel;
    case "failure":
      return episode.successLabel === false;
    case "auto":
      return episode.hasVlmLabel && !episode.hasHumanLabel;
    default:
      return true;
  }
}

function matchDispositionFilter(episode: Episode, filter: DispositionFilter): boolean {
  if (filter === "all") {
    return true;
  }
  return episode.disposition === filter;
}

function sortEpisodes(episodes: Episode[], key: SortKey, desc: boolean): Episode[] {
  const sorted = [...episodes].sort((a, b) => {
    switch (key) {
      case "quality":
        return (a.qualityScore ?? -1) - (b.qualityScore ?? -1);
      case "status": {
        const order: Record<string, number> = { pending: 0, edited: 1, accepted: 2, rejected: 3 };
        return (order[a.reviewStatus] ?? 0) - (order[b.reviewStatus] ?? 0);
      }
      default:
        return a.episodeIndex - b.episodeIndex;
    }
  });
  return desc ? sorted.reverse() : sorted;
}

export function EpisodeList({
  episodes,
  episodeTotal,
  hasMoreEpisodes = false,
  isLoadingMore = false,
  metadataFilters = DEFAULT_METADATA_FILTERS,
  isFilteringEpisodes = false,
  searchText = "",
  selectedEpisodeIndex,
  onSelectEpisode,
  onLoadMoreEpisodes,
  onMetadataFiltersChange,
  onSearchTextChange,
  onMarkDisposition,
  compact = false
}: EpisodeListProps) {
  const [filter, setFilter] = useState<QuickFilter>("all");
  const [dispositionFilter, setDispositionFilter] = useState<DispositionFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("episode_index");
  const [sortDesc, setSortDesc] = useState(false);
  const [flagTarget, setFlagTarget] = useState<{ index: number; reason: string } | null>(null);
  const [searchDraft, setSearchDraft] = useState(searchText);

  useEffect(() => {
    setSearchDraft(searchText);
  }, [searchText]);

  const filtered = episodes.filter((ep) => {
    if (!matchFilter(ep, filter)) {
      return false;
    }
    if (!matchDispositionFilter(ep, dispositionFilter)) {
      return false;
    }
    return true;
  });
  const sorted = sortEpisodes(filtered, sortKey, sortDesc);
  const total = episodeTotal ?? episodes.length;
  const countLabel =
    total > episodes.length
      ? `${filtered.length}/${episodes.length} of ${total}`
      : `${filtered.length}/${episodes.length}`;

  function handleSort() {
    const keys: SortKey[] = ["episode_index", "quality", "status"];
    const currentIdx = keys.indexOf(sortKey);
    if (sortDesc) {
      setSortKey(keys[(currentIdx + 1) % keys.length]);
      setSortDesc(false);
    } else {
      setSortDesc(true);
    }
  }

  function updateMetadataFilters(patch: Partial<EpisodeMetadataFilters>) {
    onMetadataFiltersChange?.({ ...metadataFilters, ...patch });
  }

  function applySearch(nextText = searchDraft) {
    void onSearchTextChange?.(nextText.trim());
  }

  function clearSearch() {
    setSearchDraft("");
    void onSearchTextChange?.("");
  }

  return (
    <section className={`episode-table-wrap${compact ? " episode-table-compact" : ""}`}>
      <div className="table-toolbar">
        <div className="section-title">Episodes ({countLabel})</div>
        <button className="icon-button" title={`Sort: ${sortKey} ${sortDesc ? "desc" : "asc"}`} onClick={handleSort} type="button">
          <ArrowDownUp size={16} />
        </button>
      </div>
      <div className="episode-list-filters">
        <form
          className="episode-list-search-row"
          onSubmit={(event) => {
            event.preventDefault();
            applySearch();
          }}
        >
          <label className="episode-list-search-box">
            <Search size={14} />
            <input
              aria-label="Search episode instructions"
              disabled={isFilteringEpisodes || !onSearchTextChange}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search instruction"
              value={searchDraft}
            />
          </label>
          {searchDraft || searchText ? (
            <button
              className="icon-button"
              disabled={isFilteringEpisodes || !onSearchTextChange}
              onClick={clearSearch}
              title="Clear instruction search"
              type="button"
            >
              <X size={15} />
            </button>
          ) : null}
          <button
            className="icon-button"
            disabled={
              isFilteringEpisodes ||
              !onSearchTextChange ||
              searchDraft.trim() === searchText.trim()
            }
            title="Search instructions"
            type="submit"
          >
            {isFilteringEpisodes ? <Loader2 className="spin-icon" size={15} /> : <Search size={15} />}
          </button>
        </form>
        <select
          aria-label="Filter by review status"
          className="episode-list-status-select"
          onChange={(event) => setFilter(event.target.value as QuickFilter)}
          value={filter}
        >
          {QUICK_FILTERS.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </select>
        <div className="episode-list-metadata-row">
          <select
            aria-label="Filter by instruction presence"
            className="episode-list-status-select"
            disabled={isFilteringEpisodes}
            onChange={(event) =>
              updateMetadataFilters({
                instruction: event.target.value as EpisodeMetadataFilters["instruction"]
              })
            }
            value={metadataFilters.instruction}
          >
            <option value="all">Any instruction</option>
            <option value="with_instruction">Has instruction</option>
            <option value="without_instruction">No instruction</option>
          </select>
          <select
            aria-label="Filter by wrist camera presence"
            className="episode-list-status-select"
            disabled={isFilteringEpisodes}
            onChange={(event) =>
              updateMetadataFilters({
                wristCamera: event.target.value as EpisodeMetadataFilters["wristCamera"]
              })
            }
            value={metadataFilters.wristCamera}
          >
            <option value="all">Any wrist cams</option>
            <option value="with_wrist">Has wrist cam</option>
            <option value="without_wrist">No wrist cam</option>
          </select>
        </div>
        <div className="episode-list-disposition-row">
          <div className="episode-list-filter-pills">
            {DISPOSITION_FILTERS.map((f) => (
              <button
                key={f.key}
                className={`quick-label-button${dispositionFilter === f.key ? " active" : ""}`}
                onClick={() => setDispositionFilter(f.key)}
                type="button"
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="episode-table" role="table">
        <div className="episode-row episode-header" role="row">
          <span>Episode</span>
          <span>Task</span>
          <span>Frames</span>
          <span>Status</span>
          <span>Labels</span>
          <span aria-hidden />
        </div>
        {sorted.map((episode) => {
          const isDeleted = episode.disposition === "deleted";
          const displayEpisodeIndex =
            episode.curatedEpisodeIndex ?? episode.episodeIndex;
          return (
            <div
              className={`episode-row ${episode.episodeIndex === selectedEpisodeIndex ? "selected" : ""}${isDeleted ? " episode-row-deleted" : ""}`}
              key={episode.episodeIndex}
              onClick={() => onSelectEpisode(episode.episodeIndex)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectEpisode(episode.episodeIndex);
                }
              }}
              role="row"
              tabIndex={0}
              title={episode.languageInstruction ?? episode.caption}
            >
              <span className="mono">#{displayEpisodeIndex}</span>
              <span>{episode.taskIndex}</span>
              <span>{episode.length}</span>
              <span>
                <StatusPill status={episode.reviewStatus} />
                {episode.disposition ? (
                  <span
                    className={`episode-disposition-badge ${episode.disposition}`}
                    title={
                      episode.dispositionReason
                        ? `${DISPOSITION_BADGE_LABEL[episode.disposition]} — ${episode.dispositionReason}`
                        : DISPOSITION_BADGE_LABEL[episode.disposition]
                    }
                  >
                    {DISPOSITION_BADGE_LABEL[episode.disposition]}
                  </span>
                ) : null}
                {episode.dirtyAnnotationCount > 0 ? (
                  <span
                    className="episode-dirty-badge"
                    title={`${episode.dirtyAnnotationCount} annotation${episode.dirtyAnnotationCount === 1 ? "" : "s"} not yet included in any export`}
                    aria-label="Has unapplied annotations"
                  >
                    •
                  </span>
                ) : null}
              </span>
              <span className="label-icons">
                {episode.successLabel ? <Check size={14} /> : null}
                {episode.hasVlmLabel ? <Bot size={14} /> : null}
                {episode.hasHumanLabel ? <UserCheck size={14} /> : null}
                {episode.hasInstruction ? (
                  <span title={episode.languageInstruction ?? "Has instruction"}>
                    <MessageSquareText size={14} />
                  </span>
                ) : null}
                {episode.hasWristCamera ? (
                  <span title="Has wrist camera">
                    <Camera size={14} />
                  </span>
                ) : null}
              </span>
              {onMarkDisposition ? (
                <span className="episode-row-actions" onClick={(event) => event.stopPropagation()}>
                  <button
                    type="button"
                    className={`episode-row-action${episode.disposition === "flagged" ? " is-flagged" : ""}`}
                    onClick={() =>
                      setFlagTarget({
                        index: episode.episodeIndex,
                        reason: episode.dispositionReason ?? ""
                      })
                    }
                    title={
                      episode.disposition === "flagged"
                        ? `Edit flag note${episode.dispositionReason ? ` — ${episode.dispositionReason}` : ""}`
                        : "Flag this episode (attach a memo)"
                    }
                    aria-label={`Flag episode ${displayEpisodeIndex}`}
                  >
                    <Flag size={12} />
                  </button>
                  <button
                    type="button"
                    className={`episode-row-action${isDeleted ? " is-undo" : ""}`}
                    onClick={() =>
                      onMarkDisposition(
                        episode.episodeIndex,
                        isDeleted ? null : "deleted",
                        null
                      )
                    }
                    title={isDeleted ? "Undo delete" : "Mark this episode as deleted"}
                    aria-label={
                      isDeleted
                        ? `Undo delete episode ${displayEpisodeIndex}`
                        : `Delete episode ${displayEpisodeIndex}`
                    }
                  >
                    {isDeleted ? <RotateCcw size={12} /> : <Trash2 size={12} />}
                  </button>
                </span>
              ) : (
                <span aria-hidden />
              )}
            </div>
          );
        })}
        {sorted.length === 0 ? (
          <div className="episode-list-empty" role="row">
            No episodes match the current filters.
          </div>
        ) : null}
        {hasMoreEpisodes && onLoadMoreEpisodes ? (
          <div className="episode-list-load-more" role="row">
            <button
              className="btn btn--sm"
              disabled={isLoadingMore}
              onClick={onLoadMoreEpisodes}
              type="button"
            >
              {isLoadingMore ? (
                <Loader2 className="spin-icon" size={14} />
              ) : (
                <ChevronsDown size={14} />
              )}
              <span>{isLoadingMore ? "Loading" : "Load More"}</span>
            </button>
          </div>
        ) : null}
        {flagTarget !== null && onMarkDisposition ? (
          <div
            className="modal-overlay"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                setFlagTarget(null);
              }
            }}
          >
            <div className="modal-panel" role="dialog" aria-label="Flag episode">
              <header className="modal-header">
                <div className="modal-header-title">
                  <Flag size={18} />
                  <h2>Flag episode #{flagTarget.index}</h2>
                </div>
                <button
                  type="button"
                  className="btn btn--ghost btn--icon"
                  onClick={() => setFlagTarget(null)}
                  aria-label="Close flag dialog"
                >
                  <X size={16} />
                </button>
              </header>
              <div className="modal-body">
                <form
                  className="flag-reason-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const trimmed = flagTarget.reason.trim();
                    onMarkDisposition(
                      flagTarget.index,
                      "flagged",
                      trimmed.length > 0 ? trimmed : null
                    );
                    setFlagTarget(null);
                  }}
                >
                  <label htmlFor="flag-reason-textarea">
                    Memo <span className="muted">(optional)</span>
                  </label>
                  <textarea
                    id="flag-reason-textarea"
                    autoFocus
                    rows={4}
                    value={flagTarget.reason}
                    onChange={(event) =>
                      setFlagTarget((prev) =>
                        prev ? { ...prev, reason: event.target.value } : prev
                      )
                    }
                    placeholder="Describe why this episode needs follow-up"
                  />
                </form>
              </div>
              <footer className="modal-footer">
                <button type="button" className="btn" onClick={() => setFlagTarget(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => {
                    const trimmed = flagTarget.reason.trim();
                    onMarkDisposition(
                      flagTarget.index,
                      "flagged",
                      trimmed.length > 0 ? trimmed : null
                    );
                    setFlagTarget(null);
                  }}
                >
                  <Flag size={16} />
                  <span>Save flag</span>
                </button>
              </footer>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
