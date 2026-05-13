"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Eye, EyeOff, Scissors } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { DatasetBrowser, DatasetMeta } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { useBrowseShortcuts } from "@/lib/use-browse-shortcuts";
import type { useStudioData } from "@/lib/use-studio-data";

import { EpisodeCharts } from "./episode-charts-async";

type StudioData = ReturnType<typeof useStudioData>;

type BrowseModeProps = {
  studio: StudioData;
  onSwitchToAnnotate: () => void;
  exportModalOpen: boolean;
  onToggleExport: () => void;
};

const ANNOTATION_OVERLAY_STORAGE_KEY = "rds.browse.showAnnotationOverlay";

export function BrowseMode({
  studio,
  onSwitchToAnnotate,
  exportModalOpen,
  onToggleExport
}: BrowseModeProps) {
  const handleMarkDisposition = useCallback(
    (kind: "deleted" | "flagged" | null, reason: string | null) => {
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
  const [inspectorOpen, setInspectorOpen] = useState(true);
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
      autoSaveId="rds.browse.layout-3col"
    >
      <Panel
        id="browse-side"
        order={1}
        defaultSize={20}
        minSize={12}
        maxSize={40}
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
          episodeTotal={studio.episodeTotal}
          hasMoreEpisodes={studio.episodeNextOffset !== null}
          isFilteringEpisodes={studio.episodeListStatus === "loading"}
          isLoadingMore={studio.episodeListStatus === "loading_more"}
          metadataFilters={studio.episodeMetadataFilters}
          onMetadataFiltersChange={studio.handleEpisodeMetadataFiltersChange}
          searchText={studio.episodeSearchText}
          onSearchTextChange={studio.handleEpisodeSearchTextChange}
          onLoadMoreEpisodes={studio.handleLoadMoreEpisodes}
          onSelectEpisode={studio.handleSelectEpisode}
          onMarkDisposition={(idx, kind, reason) =>
            void studio.handleSetEpisodeDisposition(idx, kind, reason)
          }
          selectedEpisodeIndex={studio.selectedEpisodeIndex}
        />
        <div className="browse-mode-side-footer">
          <button
            className="btn btn--primary btn--sm browse-side-annotate"
            onClick={onSwitchToAnnotate}
            title="Open this episode in the Annotate workspace"
            type="button"
          >
            <Scissors size={14} />
            <span>Annotate this episode &rarr;</span>
          </button>
          <button
            className={`btn btn--sm browse-side-apply${exportModalOpen ? " active" : ""}`}
            onClick={onToggleExport}
            title="Apply curated annotations, then upload to Hugging Face"
            aria-label="Open apply and upload panel"
            aria-pressed={exportModalOpen}
            type="button"
          >
            <Download size={14} />
            <span>Apply / Upload</span>
          </button>
        </div>
      </Panel>
      <PanelResizeHandle className="panel-resize-handle" />
      <Panel id="browse-stage" order={2} defaultSize={58} minSize={32} className="browse-mode-stage">
        <EpisodeViewer
          actionSemantics={studio.selectedSummary?.actionSemantics ?? null}
          annotations={annotationsForOverlay}
          episode={studio.selectedEpisode}
          initialLayout="stack"
          onFrameChange={studio.handleSelectFrame}
          selectedFrame={studio.selectedFrameIndex}
        />
        <div className="browse-mode-charts">
          <Suspense
            fallback={
              <div className="episode-charts episode-charts-empty">
                <span className="muted">Loading charts...</span>
              </div>
            }
          >
            <EpisodeCharts
              episode={studio.selectedEpisode}
              annotations={annotationsForOverlay}
              selectedFrame={studio.selectedFrameIndex}
              onSelectFrame={studio.handleSelectFrame}
            />
          </Suspense>
        </div>
        <div className="browse-mode-stage-actions">
          <span className="browse-stage-meta muted">
            Episode #
            {studio.selectedEpisode.curatedEpisodeIndex ??
              studio.selectedEpisode.episodeIndex}
            {studio.selectedEpisode.caption ? (
              <> · {studio.selectedEpisode.caption}</>
            ) : null}
          </span>
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
          <button
            type="button"
            className="btn btn--ghost btn--sm browse-details-toggle"
            onClick={() => setInspectorOpen((value) => !value)}
            aria-expanded={inspectorOpen}
            title={inspectorOpen ? "Hide dataset details" : "Show dataset details"}
          >
            {inspectorOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            <span>Details</span>
          </button>
        </div>
      </Panel>
      {inspectorOpen ? (
        <>
          <PanelResizeHandle className="panel-resize-handle" />
          <Panel
            id="browse-inspector"
            order={3}
            defaultSize={16}
            minSize={12}
            maxSize={30}
            className="browse-mode-inspector"
          >
            <div className="browse-inspector-header">
              <span>Details</span>
              <button
                type="button"
                className="btn btn--ghost btn--icon"
                onClick={() => setInspectorOpen(false)}
                title="Hide dataset details"
                aria-label="Hide dataset details"
              >
                <ChevronRight size={15} />
              </button>
            </div>
            <DatasetMeta
              health={studio.selectedDatasetHealth}
              summary={studio.selectedSummary}
            />
          </Panel>
        </>
      ) : null}
    </PanelGroup>
  );
}
