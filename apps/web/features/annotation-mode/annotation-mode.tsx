"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Wand2 } from "lucide-react";

import { AnnotationEditor } from "@/features/annotation-editor/annotation-editor";
import { AutoLabelDialog } from "@/features/annotation-mode/auto-label-dialog";
import { CheatsheetModal } from "@/features/annotation-mode/cheatsheet-modal";
import { EmptyStateCoach } from "@/features/annotation-mode/empty-state-coach";
import { IconRail } from "@/features/annotation-mode/icon-rail";
import { ShortcutChip } from "@/features/annotation-mode/shortcut-chip";
import { SkillHotBar } from "@/features/annotation-mode/skill-hot-bar";
import { StatusHud } from "@/features/annotation-mode/status-hud";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { TimelinePanel } from "@/features/episode-viewer/timeline-panel";
import { SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import { useAnnotateShortcuts } from "@/lib/use-annotate-shortcuts";
import { useAnnotationEditor } from "@/lib/use-annotation-editor";
import type { useStudioData } from "@/lib/use-studio-data";
import type { Episode, SegmentAnnotation } from "@/lib/types";

type StudioData = ReturnType<typeof useStudioData>;

type AnnotationModeProps = {
  studio: StudioData;
  showSignals: boolean;
  onToggleSignals: () => void;
  clipStart: number | null;
  clipEnd: number | null;
  onSetClipStart: (frame: number | null) => void;
  onSetClipEnd: (frame: number | null) => void;
  selectedClipId: string | null;
  onSetSelectedClipId: (id: string | null) => void;
  selectedSkillId: number;
  onSetSelectedSkillId: (id: number) => void;
  cheatsheetOpen: boolean;
  onCloseCheatsheet: () => void;
  onOpenCheatsheet: () => void;
};

export function AnnotationMode({
  studio,
  showSignals,
  onToggleSignals,
  clipStart,
  clipEnd,
  onSetClipStart,
  onSetClipEnd,
  selectedClipId,
  onSetSelectedClipId,
  selectedSkillId,
  onSetSelectedSkillId,
  cheatsheetOpen,
  onCloseCheatsheet,
  onOpenCheatsheet
}: AnnotationModeProps) {
  const editor = useAnnotationEditor();
  const fps = studio.selectedEpisode?.fps > 0 ? studio.selectedEpisode.fps : 20;
  const [autoLabelOpen, setAutoLabelOpen] = useState(false);
  const caption = studio.selectedEpisode?.caption?.trim() ?? "";

  // Track previously visited episode + its annotations so we can snapshot it
  // when the user navigates away. Captures stay client-side via useAnnotationEditor.
  const lastSeenRef = useRef<{ episode: Episode; annotations: SegmentAnnotation[] } | null>(
    null
  );
  useEffect(() => {
    const previous = lastSeenRef.current;
    const currentEpisode = studio.selectedEpisode;
    const sameEpisode =
      previous !== null &&
      previous.episode.episodeIndex === currentEpisode.episodeIndex &&
      previous.episode.datasetId === currentEpisode.datasetId;
    if (previous !== null && !sameEpisode) {
      editor.captureLastEpisode(previous.episode, previous.annotations);
    }
    lastSeenRef.current = { episode: currentEpisode, annotations: studio.annotationRows };
  }, [studio.selectedEpisode, studio.annotationRows, editor]);

  // Skill clip count for the current episode — drives the empty-state coach.
  const currentSkillClipCount = studio.annotationRows.filter(
    (row) =>
      row.datasetId === studio.selectedEpisode.datasetId &&
      row.episodeIndex === studio.selectedEpisode.episodeIndex &&
      row.labelType === SKILL_LABEL_TYPE
  ).length;

  // Auto-dismiss the coach the moment the user creates the first clip
  // for an episode they hadn't yet dismissed.
  useEffect(() => {
    if (currentSkillClipCount > 0) {
      editor.dismissCoach(studio.selectedEpisode.datasetId, studio.selectedEpisode.episodeIndex);
    }
  }, [currentSkillClipCount, studio.selectedEpisode.datasetId, studio.selectedEpisode.episodeIndex, editor]);

  const coachVisible =
    currentSkillClipCount === 0 &&
    !editor.isCoachDismissed(studio.selectedEpisode.datasetId, studio.selectedEpisode.episodeIndex);

  const handleApplyLastEpisode = useCallback(() => {
    const last = editor.lastEpisodeBoundaries;
    if (!last) {
      return;
    }
    const targetFrameCount = Math.max(1, studio.selectedEpisode.length);
    const lastMaxFrame = Math.max(1, last.frameCount - 1);
    const targetMaxFrame = Math.max(0, targetFrameCount - 1);
    for (const clip of last.clips) {
      const startRatio = clip.startFrame / lastMaxFrame;
      const endRatio = clip.endFrame / lastMaxFrame;
      const start = Math.max(0, Math.min(targetMaxFrame, Math.round(startRatio * targetMaxFrame)));
      const end = Math.max(start, Math.min(targetMaxFrame, Math.round(endRatio * targetMaxFrame)));
      void studio.handleCreateSegment({
        labelType: SKILL_LABEL_TYPE,
        labelValue: clip.skillName,
        startFrame: start,
        endFrame: end,
        reviewStatus: "accepted",
        metadata: { skillId: clip.skillId, qualityScore: null, successLabel: null }
      });
    }
  }, [editor.lastEpisodeBoundaries, studio]);

  const applyLastDisabled =
    !editor.lastEpisodeBoundaries ||
    (editor.lastEpisodeBoundaries.episodeIndex === studio.selectedEpisode.episodeIndex &&
      editor.lastEpisodeBoundaries.datasetId === studio.selectedEpisode.datasetId);
  const applyLastTitle = editor.lastEpisodeBoundaries
    ? applyLastDisabled
      ? "Captured boundaries belong to this episode — switch to another to apply"
      : `Apply ${editor.lastEpisodeBoundaries.clips.length} clip(s) from episode #${editor.lastEpisodeBoundaries.episodeIndex} (frame-ratio normalized)`
    : "No previously annotated episode to apply yet";

  useAnnotateShortcuts({
    enabled: true,
    enableBadFrameShortcuts: editor.enableBadFrameShortcuts,
    studio,
    clipStart,
    clipEnd,
    setClipStart: onSetClipStart,
    setClipEnd: onSetClipEnd,
    selectedClipId,
    setSelectedClipId: onSetSelectedClipId,
    setSelectedSkillId: onSetSelectedSkillId
  });

  return (
    <div className="annotation-mode-shell">
      <IconRail
        studio={studio}
        activePanel={editor.railPanel}
        pinned={editor.railPinned}
        onTogglePanel={editor.toggleRailPanel}
        onTogglePin={editor.togglePin}
        onOpenCheatsheet={onOpenCheatsheet}
      />
      <main className="annotation-stage">
        <div className="annotation-mode-header">
          <div className="annotation-mode-header-meta">
            <span>Episode #{studio.selectedEpisode.episodeIndex}</span>
            {caption ? <small>{caption}</small> : null}
          </div>
          <div className="annotation-mode-header-actions">
            <button
              type="button"
              className="annotation-mode-header-button primary"
              onClick={() => setAutoLabelOpen(true)}
            >
              <Wand2 size={16} />
              <span>Auto Label this episode</span>
            </button>
            <button
              type="button"
              className="annotation-mode-header-button"
              disabled={applyLastDisabled}
              onClick={handleApplyLastEpisode}
              title={applyLastTitle}
            >
              <RefreshCw size={16} />
              <span>Apply Last Episode</span>
            </button>
          </div>
        </div>
        <div className="annotation-stage-preview">
          <EpisodeViewer
            annotations={studio.annotationRows}
            episode={studio.selectedEpisode}
            onFrameChange={studio.handleSelectFrame}
            selectedFrame={studio.selectedFrameIndex}
            onToggleSignals={onToggleSignals}
            showSignals={showSignals}
          />
          {coachVisible ? (
            <EmptyStateCoach
              onDismiss={() =>
                editor.dismissCoach(
                  studio.selectedEpisode.datasetId,
                  studio.selectedEpisode.episodeIndex
                )
              }
            />
          ) : null}
        </div>
        <SkillHotBar selectedSkillId={selectedSkillId} onSelect={onSetSelectedSkillId} />
        <StatusHud
          frameIndex={studio.selectedFrameIndex}
          frameCount={studio.selectedEpisode.length}
          fps={fps}
          selectedSkillId={selectedSkillId}
          clipStart={clipStart}
          clipEnd={clipEnd}
          annotations={studio.annotationRows}
        />
        <TimelinePanel
          annotations={studio.annotationRows}
          clipEnd={clipEnd}
          clipStart={clipStart}
          fps={fps}
          frameCount={studio.selectedEpisode.length}
          onCreateSegment={studio.handleCreateSegment}
          onDeleteSegment={studio.handleDeleteSegment}
          onSelectSegment={onSetSelectedClipId}
          onMergeSegments={studio.handleMergeSegments}
          onSelectFrame={studio.handleSelectFrame}
          onSetClipEnd={onSetClipEnd}
          onSetClipStart={onSetClipStart}
          onSplitSegment={studio.handleSplitSegment}
          onUpdateSegment={studio.handleUpdateSegment}
          selectedFrame={studio.selectedFrameIndex}
          selectedSegmentId={selectedClipId}
        />
        <ShortcutChip enableBadFrameShortcuts={editor.enableBadFrameShortcuts} />
      </main>
      <aside className="annotation-inspector">
        <AnnotationEditor
          annotationHistory={studio.annotationHistoryRows}
          clipEnd={clipEnd}
          clipStart={clipStart}
          compact={false}
          onSetClipEnd={onSetClipEnd}
          onSetClipStart={onSetClipStart}
          onSetSelectedSkillId={onSetSelectedSkillId}
          annotations={studio.annotationRows}
          episode={studio.selectedEpisode}
          onCreateSegment={studio.handleCreateSegment}
          onAssignAnnotation={studio.handleAssignAnnotation}
          onDeleteSegment={studio.handleDeleteSegment}
          onRunVlmLabel={studio.handleRunVlmLabel}
          onSelectClip={onSetSelectedClipId}
          onUpdateSelectedFrameLabel={studio.handleUpdateSelectedFrameLabel}
          onUpdateSelectedFrameBadFlag={studio.handleUpdateSelectedFrameBadFlag}
          onUpdateSegment={studio.handleUpdateSegment}
          onUpdateReviewStatus={studio.handleUpdateReviewStatus}
          selectedFrame={studio.selectedFrameIndex}
          selectedFrameRecord={studio.selectedFrameRecord}
          selectedFrameStatus={studio.selectedFrameStatus}
          selectedClipId={selectedClipId}
          selectedSkillId={selectedSkillId}
          reviewerUserId={studio.reviewerUserId}
          vlmJob={studio.vlmJob}
          vlmResponses={studio.vlmResponses}
        />
      </aside>
      <CheatsheetModal
        open={cheatsheetOpen}
        onClose={onCloseCheatsheet}
        enableBadFrameShortcuts={editor.enableBadFrameShortcuts}
        onSetEnableBadFrameShortcuts={editor.setEnableBadFrameShortcuts}
      />
      <AutoLabelDialog
        open={autoLabelOpen}
        onClose={() => setAutoLabelOpen(false)}
        studio={studio}
      />
    </div>
  );
}
