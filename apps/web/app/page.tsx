"use client";

import { useState } from "react";
import { Database, Settings } from "lucide-react";

import { AnnotationEditor } from "@/features/annotation-editor/annotation-editor";
import { DatasetBrowser } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { TimelinePanel } from "@/features/episode-viewer/timeline-panel";
import { ExportStrip } from "@/features/export-manager/export-strip";
import { RerunPanel } from "@/features/rerun-viewer/rerun-panel";
import { SearchFilterBar } from "@/features/search-filter/search-filter-bar";
import { useStudioData } from "@/lib/use-studio-data";

export default function Home() {
  const [showEpisodeDrawer, setShowEpisodeDrawer] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  const {
    annotationHistoryRows,
    episodeLabelHistoryRows,
    annotationRows,
    dataStatus,
    episodeRows,
    exportJob,
    exportRecord,
    filterPresets,
    frameBrowserLimit,
    frameBrowserStart,
    framePage,
    frameRows,
    frameRowsStatus,
    mutationNotice,
    rerunJob,
    rerunSession,
    rerunViewerUrl,
    reviewQueueRows,
    reviewerUserId,
    searchResults,
    selectedEpisode,
    selectedEpisodeIndex,
    selectedDatasetHealth,
    selectedFrameIndex,
    selectedFrameRecord,
    selectedFrameStatus,
    selectedSummary,
    vlmJob,
    vlmResponses,
    handleAssignAnnotation,
    handleCreateExport,
    handleCreateFilterPreset,
    handleCreateRerunSession,
    handleCreateSegment,
    handleDeleteSegment,
    handleDeleteFilterPreset,
    handleFilterSearch,
    handleFullTextSearch,
    handleMergeSegments,
    handleOpenDataset,
    handleRunVlmLabel,
    handleSelectEpisode,
    handleSelectFrame,
    handleDismissMutationNotice,
    handleSemanticSearch,
    handleSetFrameBrowserLimit,
    handleSetFrameBrowserStart,
    handleSplitSegment,
    handleUpdateEpisodeLabels,
    handleUpdateFrameBadFlag,
    handleUpdateSelectedFrameLabel,
    handleUpdateSelectedFrameBadFlag,
    handleUpdateSegment,
    handleUpdateReviewStatus
  } = useStudioData();

  return (
    <div className="studio-shell">
      <header className="top-bar">
        <div className="brand">
          <Database size={18} />
          <span>Robot Data Studio</span>
        </div>
        <nav className="top-nav">
          <button className="nav-button active" type="button">
            Dataset
          </button>
          <button className="nav-button" type="button">
            Episodes
          </button>
          <button className="nav-button" type="button">
            Review
          </button>
        </nav>
        <button className="icon-button" title="Advanced settings" type="button">
          <Settings size={17} />
        </button>
      </header>

      <div className={`data-source-banner data-source-${dataStatus}`}>
        {dataStatus === "loading"
          ? "Loading API datasets"
          : dataStatus === "api"
            ? `API dataset: ${selectedSummary.name}`
            : "Sample data fallback"}
      </div>
      {mutationNotice ? (
        <div className="data-source-banner data-source-sample">
          <span>{mutationNotice}</span>
          <button className="text-button compact-text-button" onClick={handleDismissMutationNotice} type="button">
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="workspace">
        <DatasetBrowser
          onOpenDataset={handleOpenDataset}
          onSelectEpisode={handleSelectEpisode}
          reviewQueueRows={reviewQueueRows}
          reviewerUserId={reviewerUserId}
          health={selectedDatasetHealth}
          summary={selectedSummary}
        />
        <div className="center-column">
          <SearchFilterBar
            filterPresets={filterPresets}
            onCreateFilterPreset={handleCreateFilterPreset}
            onDeleteFilterPreset={handleDeleteFilterPreset}
            onFilterSearch={handleFilterSearch}
            onFullTextSearch={handleFullTextSearch}
            onSelectResult={handleSelectEpisode}
            onSemanticSearch={handleSemanticSearch}
            results={searchResults}
          />
          <div className="review-action-bar">
            <button
              className={`text-button compact-text-button${showEpisodeDrawer ? " active" : ""}`}
              onClick={() => setShowEpisodeDrawer((current) => !current)}
              type="button"
            >
              Episodes ({episodeRows.length})
            </button>
            <button
              className={`text-button compact-text-button${showSignals ? " active" : ""}`}
              onClick={() => setShowSignals((current) => !current)}
              type="button"
            >
              Signals
            </button>
          </div>
          {showEpisodeDrawer ? (
            <EpisodeList
              compact
              episodes={episodeRows}
              onSelectEpisode={handleSelectEpisode}
              selectedEpisodeIndex={selectedEpisodeIndex}
            />
          ) : null}
          <div className="content-split">
            <div className="viewer-column">
              <EpisodeViewer
                annotations={annotationRows}
                episode={selectedEpisode}
                onFrameChange={handleSelectFrame}
                selectedFrame={selectedFrameIndex}
                onToggleSignals={() => setShowSignals((current) => !current)}
                showSignals={showSignals}
              />
              <TimelinePanel
                annotations={annotationRows}
                frameCount={selectedEpisode.length}
                onCreateSegment={handleCreateSegment}
                onDeleteSegment={handleDeleteSegment}
                onMergeSegments={handleMergeSegments}
                onSelectFrame={handleSelectFrame}
                onSplitSegment={handleSplitSegment}
                onUpdateSegment={handleUpdateSegment}
                selectedFrame={selectedFrameIndex}
              />
              <RerunPanel
                job={rerunJob}
                onCreateSession={handleCreateRerunSession}
                session={rerunSession}
                viewerUrl={rerunViewerUrl}
              />
            </div>
            <AnnotationEditor
              annotationHistory={annotationHistoryRows}
              episodeLabelHistory={episodeLabelHistoryRows}
              annotations={annotationRows}
              episode={selectedEpisode}
              frameRows={frameRows}
              frameRowsStatus={frameRowsStatus}
              frameBrowserLimit={frameBrowserLimit}
              frameBrowserStart={frameBrowserStart}
              framePage={framePage}
              onCreateSegment={handleCreateSegment}
              onAssignAnnotation={handleAssignAnnotation}
              onDeleteSegment={handleDeleteSegment}
              onRunVlmLabel={handleRunVlmLabel}
              onSelectFrame={handleSelectFrame}
              onSplitSegment={handleSplitSegment}
              onUpdateEpisodeLabels={handleUpdateEpisodeLabels}
              onUpdateFrameBadFlag={handleUpdateFrameBadFlag}
              onSetFrameBrowserLimit={handleSetFrameBrowserLimit}
              onSetFrameBrowserStart={handleSetFrameBrowserStart}
              onUpdateSelectedFrameLabel={handleUpdateSelectedFrameLabel}
              onUpdateSelectedFrameBadFlag={handleUpdateSelectedFrameBadFlag}
              onUpdateSegment={handleUpdateSegment}
              onUpdateReviewStatus={handleUpdateReviewStatus}
              selectedFrame={selectedFrameIndex}
              selectedFrameRecord={selectedFrameRecord}
              selectedFrameStatus={selectedFrameStatus}
              reviewerUserId={reviewerUserId}
              vlmJob={vlmJob}
              vlmResponses={vlmResponses}
            />
          </div>
          <ExportStrip
            episodeIndex={selectedEpisode.episodeIndex}
            exportJob={exportJob}
            exportRecord={exportRecord}
            onCreateExport={handleCreateExport}
            split={selectedEpisode.split}
          />
        </div>
      </div>
    </div>
  );
}
