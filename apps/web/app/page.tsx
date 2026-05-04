"use client";

import { Bot, Database, Download, Settings } from "lucide-react";

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
  const {
    annotationRows,
    dataStatus,
    episodeRows,
    exportRecord,
    filterPresets,
    rerunSession,
    rerunViewerUrl,
    searchResults,
    selectedEpisode,
    selectedEpisodeIndex,
    selectedSummary,
    vlmJob,
    handleCreateExport,
    handleCreateFilterPreset,
    handleCreateRerunSession,
    handleCreateSegment,
    handleDeleteSegment,
    handleDeleteFilterPreset,
    handleFilterSearch,
    handleMergeSegments,
    handleOpenDataset,
    handleRunVlmLabel,
    handleSelectEpisode,
    handleSemanticSearch,
    handleSplitSegment,
    handleUpdateEpisodeLabels,
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
            Task
          </button>
          <button className="nav-button" type="button">
            Search
          </button>
          <button className="nav-button" type="button">
            <Bot size={15} />
            VLM Jobs
          </button>
          <button className="nav-button" type="button">
            <Download size={15} />
            Export
          </button>
        </nav>
        <button className="icon-button" title="Settings" type="button">
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

      <div className="workspace">
        <DatasetBrowser onOpenDataset={handleOpenDataset} summary={selectedSummary} />
        <div className="center-column">
          <SearchFilterBar
            filterPresets={filterPresets}
            onCreateFilterPreset={handleCreateFilterPreset}
            onDeleteFilterPreset={handleDeleteFilterPreset}
            onFilterSearch={handleFilterSearch}
            onSelectResult={handleSelectEpisode}
            onSemanticSearch={handleSemanticSearch}
            results={searchResults}
          />
          <div className="content-split">
            <div className="viewer-column">
              <EpisodeViewer episode={selectedEpisode} />
              <TimelinePanel
                annotations={annotationRows}
                frameCount={selectedEpisode.length}
                onCreateSegment={handleCreateSegment}
                onDeleteSegment={handleDeleteSegment}
                onMergeSegments={handleMergeSegments}
                onSplitSegment={handleSplitSegment}
                onUpdateSegment={handleUpdateSegment}
              />
              <RerunPanel
                onCreateSession={handleCreateRerunSession}
                session={rerunSession}
                viewerUrl={rerunViewerUrl}
              />
            </div>
            <AnnotationEditor
              annotations={annotationRows}
              episode={selectedEpisode}
              onCreateSegment={handleCreateSegment}
              onDeleteSegment={handleDeleteSegment}
              onRunVlmLabel={handleRunVlmLabel}
              onSplitSegment={handleSplitSegment}
              onUpdateEpisodeLabels={handleUpdateEpisodeLabels}
              onUpdateSegment={handleUpdateSegment}
              onUpdateReviewStatus={handleUpdateReviewStatus}
              vlmJob={vlmJob}
            />
          </div>
          <ExportStrip
            episodeIndex={selectedEpisode.episodeIndex}
            exportRecord={exportRecord}
            onCreateExport={handleCreateExport}
          />
        </div>
        <EpisodeList
          episodes={episodeRows}
          onSelectEpisode={handleSelectEpisode}
          selectedEpisodeIndex={selectedEpisodeIndex}
        />
      </div>
    </div>
  );
}
