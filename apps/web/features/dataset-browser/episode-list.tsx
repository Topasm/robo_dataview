"use client";

import { useState } from "react";
import { ArrowDownUp, Bot, Check, UserCheck } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { Episode, EpisodeDisposition } from "@/lib/types";

type EpisodeListProps = {
  episodes: Episode[];
  selectedEpisodeIndex: number;
  onSelectEpisode: (episodeIndex: number) => void;
  compact?: boolean;
};

type QuickFilter = "all" | "need_check" | "bad" | "no_label" | "failure" | "auto";
type SortKey = "episode_index" | "quality" | "status";
type DispositionFilter = "all" | EpisodeDisposition;

const QUICK_FILTERS: { key: QuickFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "need_check", label: "Need Check" },
  { key: "bad", label: "Bad/Drop" },
  { key: "no_label", label: "No Label" },
  { key: "failure", label: "Failure" },
  { key: "auto", label: "Auto Labels" }
];

const DISPOSITION_FILTERS: { key: DispositionFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "kept", label: "Kept" },
  { key: "deleted", label: "Deleted" },
  { key: "flagged", label: "Flagged" }
];

const DISPOSITION_BADGE_LABEL: Record<EpisodeDisposition, string> = {
  kept: "Kept",
  deleted: "Deleted",
  flagged: "Flagged"
};

function matchFilter(episode: Episode, filter: QuickFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "need_check":
      return episode.reviewStatus === "pending";
    case "bad":
      return episode.reviewStatus === "rejected";
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
  selectedEpisodeIndex,
  onSelectEpisode,
  compact = false
}: EpisodeListProps) {
  const [filter, setFilter] = useState<QuickFilter>("all");
  const [dispositionFilter, setDispositionFilter] = useState<DispositionFilter>("all");
  const [hideDeleted, setHideDeleted] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("episode_index");
  const [sortDesc, setSortDesc] = useState(false);

  const filtered = episodes.filter((ep) => {
    if (!matchFilter(ep, filter)) {
      return false;
    }
    if (!matchDispositionFilter(ep, dispositionFilter)) {
      return false;
    }
    if (hideDeleted && dispositionFilter === "all" && ep.disposition === "deleted") {
      return false;
    }
    return true;
  });
  const sorted = sortEpisodes(filtered, sortKey, sortDesc);

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

  return (
    <section className={`episode-table-wrap${compact ? " episode-table-compact" : ""}`}>
      <div className="table-toolbar">
        <div className="section-title">Episodes ({filtered.length}/{episodes.length})</div>
        <button className="icon-button" title={`Sort: ${sortKey} ${sortDesc ? "desc" : "asc"}`} onClick={handleSort} type="button">
          <ArrowDownUp size={16} />
        </button>
      </div>
      <div className="frame-quick-labels" style={{ marginBottom: "8px" }}>
        {QUICK_FILTERS.map((f) => (
          <button
            key={f.key}
            className={`quick-label-button${filter === f.key ? " active" : ""}`}
            onClick={() => setFilter(f.key)}
            type="button"
          >
            {f.label}
          </button>
        ))}
      </div>
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
      <label className="episode-list-filter-toggle">
        <input
          type="checkbox"
          checked={hideDeleted}
          disabled={dispositionFilter === "deleted"}
          onChange={(event) => setHideDeleted(event.target.checked)}
        />
        <span>Hide deleted</span>
      </label>
      <div className="episode-table" role="table">
        <div className="episode-row episode-header" role="row">
          <span>Episode</span>
          <span>Task</span>
          <span>Frames</span>
          <span>Status</span>
          <span>Quality</span>
          <span>Labels</span>
        </div>
        {sorted.map((episode) => {
          const isDeleted = episode.disposition === "deleted";
          return (
            <button
              className={`episode-row ${episode.episodeIndex === selectedEpisodeIndex ? "selected" : ""}${isDeleted ? " episode-row-deleted" : ""}`}
              key={episode.episodeIndex}
              onClick={() => onSelectEpisode(episode.episodeIndex)}
              role="row"
              type="button"
            >
              <span className="mono">#{episode.episodeIndex}</span>
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
              </span>
              <span>{episode.qualityScore === null ? "n/a" : episode.qualityScore.toFixed(2)}</span>
              <span className="label-icons">
                {episode.successLabel ? <Check size={14} /> : null}
                {episode.hasVlmLabel ? <Bot size={14} /> : null}
                {episode.hasHumanLabel ? <UserCheck size={14} /> : null}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
