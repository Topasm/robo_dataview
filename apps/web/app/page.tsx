"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Database, Download, Settings } from "lucide-react";

import { AnnotationEditor } from "@/features/annotation-editor/annotation-editor";
import { DatasetBrowser } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { FrameTablePanel } from "@/features/episode-viewer/frame-table-panel";
import { TimelinePanel } from "@/features/episode-viewer/timeline-panel";
import { ExportStrip } from "@/features/export-manager/export-strip";
import { RerunPanel } from "@/features/rerun-viewer/rerun-panel";
import { SearchFilterBar } from "@/features/search-filter/search-filter-bar";
import { HUMANOID_SKILLS, SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import { useStudioData } from "@/lib/use-studio-data";

type DrawerTab = "episodes" | "frames" | "rerun" | "export";

export default function Home() {
  const [workMode, setWorkMode] = useState<"view" | "segment">("view");
  const [activeDrawer, setActiveDrawer] = useState<DrawerTab | null>(null);
  const [showSignals, setShowSignals] = useState(false);
  const [clipStart, setClipStart] = useState<number | null>(null);
  const [clipEnd, setClipEnd] = useState<number | null>(null);
  const [selectedSkillId, setSelectedSkillId] = useState<number>(0);
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
  const lastFrame = Math.max(0, (selectedEpisode?.length ?? 1) - 1);
  const fps = selectedEpisode?.fps > 0 ? selectedEpisode.fps : 20;

  useEffect(() => {
    setClipStart(null);
    setClipEnd(null);
  }, [selectedEpisode.datasetId, selectedEpisode.episodeIndex]);

  const handleSelectNextPendingEpisode = useCallback(() => {
    const nextPending = episodeRows.find(ep => ep.reviewStatus === "pending" && ep.episodeIndex !== selectedEpisodeIndex);
    if (nextPending) {
      handleSelectEpisode(nextPending.episodeIndex);
    }
  }, [episodeRows, selectedEpisodeIndex, handleSelectEpisode]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTyping) {
        return;
      }
      // --- Navigation / playback ---
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        handleSelectFrame(Math.max(0, selectedFrameIndex - (event.shiftKey ? 10 : 1)));
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        handleSelectFrame(Math.min(lastFrame, selectedFrameIndex + (event.shiftKey ? 10 : 1)));
      } else if (event.key === "Escape") {
        event.preventDefault();
        setActiveDrawer(null);
      // --- Skill clip boundary ---
      } else if (event.key.toLowerCase() === "i") {
        event.preventDefault();
        setClipStart(selectedFrameIndex);
      } else if (event.key.toLowerCase() === "o") {
        event.preventDefault();
        setClipEnd(selectedFrameIndex);
      } else if (event.key.toLowerCase() === "a" && clipStart !== null && clipEnd !== null) {
        event.preventDefault();
        const skill = HUMANOID_SKILLS[selectedSkillId];
        if (skill) {
          const start = Math.min(clipStart, clipEnd);
          const end = Math.max(clipStart, clipEnd);
          void handleCreateSegment({ labelType: SKILL_LABEL_TYPE, labelValue: skill.name, startFrame: start, endFrame: end });
          setClipStart(null);
          setClipEnd(null);
        }
      } else if (event.key === "Enter") {
        event.preventDefault();
        // Accept is handled inside AnnotationEditor via selected clip
      } else if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        // Delete is handled inside AnnotationEditor via selected clip
      // --- Skill ID selection (0-9) ---
      } else if (event.key >= "0" && event.key <= "9") {
        event.preventDefault();
        const id = Number(event.key);
        if (id < HUMANOID_SKILLS.length) {
          setSelectedSkillId(id);
        }
      // --- Frame tools ---
      } else if (event.key.toLowerCase() === "m") {
        event.preventDefault();
        void handleUpdateSelectedFrameBadFlag(!(selectedFrameRecord?.isBadFrame ?? false));
      } else if (event.key.toLowerCase() === "b") {
        event.preventDefault();
        const radius = Math.max(1, Math.round(fps / 2));
        void handleCreateSegment({ labelType: "bad_range", labelValue: "bad_range", startFrame: Math.max(0, selectedFrameIndex - radius), endFrame: Math.min(lastFrame, selectedFrameIndex + radius) });
      // --- Drawer toggles ---
      } else if (event.key.toLowerCase() === "e") {
        event.preventDefault();
        setActiveDrawer((current) => (current === "episodes" ? null : "episodes"));
      } else if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        setActiveDrawer((current) => (current === "frames" ? null : "frames"));
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        setActiveDrawer((current) => (current === "rerun" ? null : "rerun"));
      } else if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        handleSelectNextPendingEpisode();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    clipEnd,
    clipStart,
    fps,
    handleCreateSegment,
    handleSelectFrame,
    handleSelectNextPendingEpisode,
    handleUpdateSelectedFrameBadFlag,
    lastFrame,
    selectedFrameIndex,
    selectedFrameRecord?.isBadFrame,
    selectedSkillId
  ]);

  return (
    <div className="studio-shell">
      <header className="top-bar">
        <div className="brand">
          <Database size={18} />
          <span>Robot Data Studio</span>
        </div>
        <nav className="top-nav">
          <button
            className={`nav-button ${workMode === "view" ? "active" : ""}`}
            onClick={() => setWorkMode("view")}
            type="button"
          >
            View
          </button>
          <button
            className={`nav-button ${workMode === "segment" ? "active" : ""}`}
            onClick={() => setWorkMode("segment")}
            type="button"
          >
            Segment
          </button>
        </nav>
        <div className="top-bar-actions">
          <button
            className={`text-button primary-export-button compact-text-button${activeDrawer === "export" ? " active" : ""}`}
            onClick={() => setActiveDrawer((current) => (current === "export" ? null : "export"))}
            type="button"
          >
            <Download size={15} />
            Export
          </button>
          <button className="icon-button" title="Advanced settings" type="button">
            <Settings size={17} />
          </button>
        </div>
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
            <div className="drawer-buttons">
              <button
                className={`text-button compact-text-button${activeDrawer === "episodes" ? " active" : ""}`}
                onClick={() => setActiveDrawer((current) => (current === "episodes" ? null : "episodes"))}
                type="button"
              >
                Episodes ({episodeRows.length})
              </button>
              <button
                className={`text-button compact-text-button${activeDrawer === "frames" ? " active" : ""}`}
                onClick={() => setActiveDrawer((current) => (current === "frames" ? null : "frames"))}
                type="button"
              >
                Frames
              </button>
              <button
                className={`text-button compact-text-button${showSignals ? " active" : ""}`}
                onClick={() => setShowSignals((current) => !current)}
                type="button"
              >
                Signals
              </button>
              <button
                className={`text-button compact-text-button${activeDrawer === "rerun" ? " active" : ""}`}
                onClick={() => setActiveDrawer((current) => (current === "rerun" ? null : "rerun"))}
                type="button"
              >
                Rerun
              </button>
            </div>
          </div>
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
                clipEnd={clipEnd}
                clipStart={clipStart}
                fps={fps}
                frameCount={selectedEpisode.length}
                onCreateSegment={handleCreateSegment}
                onDeleteSegment={handleDeleteSegment}
                onMergeSegments={handleMergeSegments}
                onSelectFrame={handleSelectFrame}
                onSetClipEnd={setClipEnd}
                onSetClipStart={setClipStart}
                onSplitSegment={handleSplitSegment}
                onUpdateSegment={handleUpdateSegment}
                selectedFrame={selectedFrameIndex}
              />
            </div>
            <AnnotationEditor
              annotationHistory={annotationHistoryRows}
              clipEnd={clipEnd}
              clipStart={clipStart}
              compact={workMode === "view"}
              onNextPendingEpisode={handleSelectNextPendingEpisode}
              onSetClipEnd={setClipEnd}
              onSetClipStart={setClipStart}
              onSetSelectedSkillId={setSelectedSkillId}
              episodeLabelHistory={episodeLabelHistoryRows}
              annotations={annotationRows}
              episode={selectedEpisode}
              onCreateSegment={handleCreateSegment}
              onAssignAnnotation={handleAssignAnnotation}
              onDeleteSegment={handleDeleteSegment}
              onRunVlmLabel={handleRunVlmLabel}
              onUpdateEpisodeLabels={handleUpdateEpisodeLabels}
              onUpdateSelectedFrameLabel={handleUpdateSelectedFrameLabel}
              onUpdateSelectedFrameBadFlag={handleUpdateSelectedFrameBadFlag}
              onUpdateSegment={handleUpdateSegment}
              onUpdateReviewStatus={handleUpdateReviewStatus}
              selectedFrame={selectedFrameIndex}
              selectedFrameRecord={selectedFrameRecord}
              selectedFrameStatus={selectedFrameStatus}
              selectedSkillId={selectedSkillId}
              reviewerUserId={reviewerUserId}
              vlmJob={vlmJob}
              vlmResponses={vlmResponses}
            />
          </div>
          {activeDrawer ? (
            <BottomDrawer
              onClose={() => setActiveDrawer(null)}
              title={drawerTitle(activeDrawer)}
            >
              {activeDrawer === "episodes" ? (
                <EpisodeList
                  compact
                  episodes={episodeRows}
                  onSelectEpisode={handleSelectEpisode}
                  selectedEpisodeIndex={selectedEpisodeIndex}
                />
              ) : null}
              {activeDrawer === "frames" ? (
                <FrameTablePanel
                  frameCount={framePage?.frameCount ?? selectedEpisode.length}
                  frameLimit={frameBrowserLimit}
                  frameStart={frameBrowserStart}
                  frames={frameRows}
                  onFrameLimitChange={handleSetFrameBrowserLimit}
                  onFrameStartChange={handleSetFrameBrowserStart}
                  onSelectFrame={handleSelectFrame}
                  onSetBadFrame={handleUpdateFrameBadFlag}
                  returnedCount={framePage?.returnedCount ?? frameRows.length}
                  selectedFrame={selectedFrameIndex}
                  status={frameRowsStatus}
                />
              ) : null}
              {activeDrawer === "rerun" ? (
                <RerunPanel
                  job={rerunJob}
                  onCreateSession={handleCreateRerunSession}
                  session={rerunSession}
                  viewerUrl={rerunViewerUrl}
                />
              ) : null}
              {activeDrawer === "export" ? (
                <ExportStrip
                  episodeIndex={selectedEpisode.episodeIndex}
                  exportJob={exportJob}
                  exportRecord={exportRecord}
                  onCreateExport={handleCreateExport}
                  split={selectedEpisode.split}
                />
              ) : null}
            </BottomDrawer>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function BottomDrawer({
  children,
  onClose,
  title
}: {
  children: ReactNode;
  onClose: () => void;
  title: string;
}) {
  return (
    <section className="bottom-drawer">
      <div className="bottom-drawer-header">
        <div className="section-title">{title}</div>
        <button className="text-button compact-text-button" onClick={onClose} type="button">
          Close
        </button>
      </div>
      <div className="bottom-drawer-body">{children}</div>
    </section>
  );
}

function drawerTitle(tab: DrawerTab): string {
  if (tab === "episodes") {
    return "Episodes";
  }
  if (tab === "frames") {
    return "Frame Browser";
  }
  if (tab === "rerun") {
    return "Rerun";
  }
  return "Export";
}
