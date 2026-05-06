"use client";

import { useState } from "react";
import { ArrowDownUp, Bot, Check, UserCheck } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { Episode } from "@/lib/types";

type EpisodeListProps = {
  episodes: Episode[];
  selectedEpisodeIndex: number;
  onSelectEpisode: (episodeIndex: number) => void;
  compact?: boolean;
};

type QuickFilter = "all" | "need_check" | "bad" | "no_label" | "failure" | "auto";
type SortKey = "episode_index" | "quality" | "status";

const QUICK_FILTERS: { key: QuickFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "need_check", label: "Need Check" },
  { key: "bad", label: "Bad/Drop" },
  { key: "no_label", label: "No Label" },
  { key: "failure", label: "Failure" },
  { key: "auto", label: "Auto Labels" }
];

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
  const [sortKey, setSortKey] = useState<SortKey>("episode_index");
  const [sortDesc, setSortDesc] = useState(false);

  const filtered = episodes.filter((ep) => matchFilter(ep, filter));
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
      <div className="episode-table" role="table">
        <div className="episode-row episode-header" role="row">
          <span>Episode</span>
          <span>Task</span>
          <span>Frames</span>
          <span>Status</span>
          <span>Quality</span>
          <span>Labels</span>
        </div>
        {sorted.map((episode) => (
          <button
            className={`episode-row ${episode.episodeIndex === selectedEpisodeIndex ? "selected" : ""}`}
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
            </span>
            <span>{episode.qualityScore === null ? "n/a" : episode.qualityScore.toFixed(2)}</span>
            <span className="label-icons">
              {episode.successLabel ? <Check size={14} /> : null}
              {episode.hasVlmLabel ? <Bot size={14} /> : null}
              {episode.hasHumanLabel ? <UserCheck size={14} /> : null}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
