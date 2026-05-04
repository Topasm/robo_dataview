"use client";

import { ArrowDownUp, Bot, Check, UserCheck } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { Episode } from "@/lib/types";

type EpisodeListProps = {
  episodes: Episode[];
  selectedEpisodeIndex: number;
  onSelectEpisode: (episodeIndex: number) => void;
};

export function EpisodeList({
  episodes,
  selectedEpisodeIndex,
  onSelectEpisode
}: EpisodeListProps) {
  return (
    <section className="episode-table-wrap">
      <div className="table-toolbar">
        <div className="section-title">Episodes</div>
        <button className="icon-button" title="Sort episodes" type="button">
          <ArrowDownUp size={16} />
        </button>
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
        {episodes.map((episode) => (
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
            <span>{episode.qualityScore.toFixed(2)}</span>
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
