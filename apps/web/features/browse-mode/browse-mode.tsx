"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { DatasetBrowser, DatasetMeta } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { useBrowseShortcuts } from "@/lib/use-browse-shortcuts";
import type { useStudioData } from "@/lib/use-studio-data";

import { EpisodeActionBar } from "./episode-action-bar";
import { EpisodeCharts } from "./episode-charts-async";

type StudioData = ReturnType<typeof useStudioData>;

type BrowseModeProps = {
  studio: StudioData;
  onSwitchToAnnotate: () => void;
};

const ANNOTATION_OVERLAY_STORAGE_KEY = "rds.browse.showAnnotationOverlay";

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

  // Strict-triage toggle: when off, charts and viewer drop the skill-clip
  // annotation overlays so Browse mirrors a raw playback view. Persisted in
  // localStorage so the choice survives page reloads.
  const [showAnnotations, setShowAnnotations] = useState(true);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(ANNOTATION_OVERLAY_STORAGE_KEY);
    if (stored !== null) setShowAnnotations(stored !== "0");
  }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      ANNOTATION_OVERLAY_STORAGE_KEY,
      showAnnotations ? "1" : "0"
    );
  }, [showAnnotations]);
  const annotationsForOverlay = showAnnotations ? studio.annotationRows : [];

  return (
    <PanelGroup
      direction="horizontal"
      className="browse-mode-shell"
      autoSaveId="rds.browse.layout"
    >
      <Panel
        id="browse-side"
        order={1}
        defaultSize={22}
        minSize={14}
        maxSize={45}
        className="browse-mode-side"
      >
        <DatasetBrowser
          onOpenDataset={studio.handleOpenDataset}
          onSelectDataset={studio.handleSelectDataset}
          selectedDatasetId={studio.selectedDatasetId}
          summaries={studio.summaries}
        />
        <EpisodeList
          compact={false}
          episodes={studio.episodeRows}
          onSelectEpisode={studio.handleSelectEpisode}
          selectedEpisodeIndex={studio.selectedEpisodeIndex}
        />
        <DatasetMeta
          health={studio.selectedDatasetHealth}
          summary={studio.selectedSummary}
        />
      </Panel>
      <PanelResizeHandle className="panel-resize-handle" />
      <Panel id="browse-stage" order={2} defaultSize={78} minSize={40} className="browse-mode-stage">
        <EpisodeViewer
          annotations={annotationsForOverlay}
          episode={studio.selectedEpisode}
          initialLayout="stack"
          onFrameChange={studio.handleSelectFrame}
          selectedFrame={studio.selectedFrameIndex}
        />
        <div className="browse-mode-charts">
          <EpisodeCharts
            episode={studio.selectedEpisode}
            annotations={annotationsForOverlay}
            selectedFrame={studio.selectedFrameIndex}
            onSelectFrame={studio.handleSelectFrame}
          />
        </div>
        <div className="browse-mode-stage-actions">
          <button
            type="button"
            className="btn btn--ghost btn--sm browse-overlay-toggle"
            onClick={() => setShowAnnotations((value) => !value)}
            title={
              showAnnotations
                ? "Hide skill-clip overlays for strict triage"
                : "Show skill-clip overlays from existing annotations"
            }
            aria-pressed={showAnnotations}
          >
            {showAnnotations ? <Eye size={14} /> : <EyeOff size={14} />}
            <span>{showAnnotations ? "Overlays on" : "Overlays off"}</span>
          </button>
          <EpisodeActionBar
            episodeCaption={studio.selectedEpisode.caption}
            episodeIndex={studio.selectedEpisode.episodeIndex}
            onMarkDisposition={handleMarkDisposition}
            onSwitchToAnnotate={onSwitchToAnnotate}
          />
        </div>
      </Panel>
    </PanelGroup>
  );
}
