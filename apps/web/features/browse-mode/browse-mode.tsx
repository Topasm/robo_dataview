"use client";

import { useCallback } from "react";

import { DatasetBrowser } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { useBrowseShortcuts } from "@/lib/use-browse-shortcuts";
import type { useStudioData } from "@/lib/use-studio-data";

import { EpisodeActionBar } from "./episode-action-bar";

type StudioData = ReturnType<typeof useStudioData>;

type BrowseModeProps = {
  studio: StudioData;
  onSwitchToAnnotate: () => void;
};

export function BrowseMode({ studio, onSwitchToAnnotate }: BrowseModeProps) {
  const handleMarkDisposition = useCallback(
    (kind: "kept" | "deleted" | "flagged", reason: string | null) => {
      void studio.handleSetEpisodeDisposition(
        studio.selectedEpisode.episodeIndex,
        kind,
        reason
      );
    },
    [studio]
  );

  useBrowseShortcuts({
    enabled: true,
    studio,
    onSwitchToAnnotate,
    onMarkDisposition: handleMarkDisposition
  });

  return (
    <div className="browse-mode-shell">
      <div className="browse-mode-side">
        <DatasetBrowser
          health={studio.selectedDatasetHealth}
          onOpenDataset={studio.handleOpenDataset}
          onSelectEpisode={studio.handleSelectEpisode}
          reviewQueueRows={studio.reviewQueueRows}
          reviewerUserId={studio.reviewerUserId}
          summary={studio.selectedSummary}
        />
        <EpisodeList
          compact={false}
          episodes={studio.episodeRows}
          onSelectEpisode={studio.handleSelectEpisode}
          selectedEpisodeIndex={studio.selectedEpisodeIndex}
        />
      </div>
      <div className="browse-mode-stage">
        <EpisodeViewer
          annotations={studio.annotationRows}
          episode={studio.selectedEpisode}
          initialLayout="grid"
          onFrameChange={studio.handleSelectFrame}
          selectedFrame={studio.selectedFrameIndex}
        />
        <div className="browse-mode-stage-actions">
          <EpisodeActionBar
            episodeCaption={studio.selectedEpisode.caption}
            episodeIndex={studio.selectedEpisode.episodeIndex}
            onMarkDisposition={handleMarkDisposition}
            onSwitchToAnnotate={onSwitchToAnnotate}
          />
        </div>
      </div>
    </div>
  );
}
