import { GitBranch, MapPin, Merge, OctagonAlert, Trash2 } from "lucide-react";
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import type { SegmentAnnotation } from "@/lib/types";

type SegmentDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
};

type TimelinePanelProps = {
  annotations: SegmentAnnotation[];
  frameCount: number;
  onCreateSegment: (draft: SegmentDraft) => Promise<void>;
  onDeleteSegment: (annotationId: string) => Promise<void>;
  onMergeSegments: (left: SegmentAnnotation, right: SegmentAnnotation) => Promise<void>;
  onSelectFrame: (frameIndex: number) => void;
  onSplitSegment: (annotation: SegmentAnnotation) => Promise<void>;
  onUpdateSegment: (annotationId: string, draft: SegmentDraft) => Promise<void>;
  selectedFrame: number;
};

type DragState = {
  annotation: SegmentAnnotation;
  edge: "start" | "end";
};

export function TimelinePanel({
  annotations,
  frameCount,
  onCreateSegment,
  onDeleteSegment,
  onMergeSegments,
  onSelectFrame,
  onSplitSegment,
  onUpdateSegment,
  selectedFrame
}: TimelinePanelProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [draftBounds, setDraftBounds] = useState<Record<string, { startFrame: number; endFrame: number }>>({});
  const safeFrameCount = Math.max(1, frameCount);
  const maxFrame = Math.max(0, safeFrameCount - 1);
  const activeFrame = clampFrame(selectedFrame, maxFrame);
  const sortedAnnotations = useMemo(
    () => [...annotations].sort((left, right) => left.startFrame - right.startFrame),
    [annotations]
  );

  const rulerValues = useMemo(
    () => [0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round(maxFrame * ratio)),
    [maxFrame]
  );

  async function handleCreateMarker() {
    await onCreateSegment({
      labelType: "important_frame",
      labelValue: "important_frame",
      startFrame: activeFrame,
      endFrame: activeFrame
    });
  }

  async function handleCreateBadRange() {
    const startFrame = clampFrame(activeFrame - 5, maxFrame);
    const endFrame = clampFrame(activeFrame + 5, maxFrame);
    await onCreateSegment({
      labelType: "bad_range",
      labelValue: "bad_range",
      startFrame,
      endFrame
    });
  }

  function handleTrackPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) {
      return;
    }
    onSelectFrame(frameFromPointer(event, trackRef.current, maxFrame));
  }

  function handleDragPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragState === null) {
      return;
    }
    const frame = frameFromPointer(event, trackRef.current, maxFrame);
    const current = draftBounds[dragState.annotation.id] ?? {
      startFrame: dragState.annotation.startFrame,
      endFrame: dragState.annotation.endFrame
    };
    const next =
      dragState.edge === "start"
        ? {
            ...current,
            startFrame: Math.min(frame, current.endFrame)
          }
        : {
            ...current,
            endFrame: Math.max(frame, current.startFrame)
          };
    setDraftBounds((bounds) => ({ ...bounds, [dragState.annotation.id]: next }));
  }

  async function handleDragPointerUp() {
    if (dragState === null) {
      return;
    }
    const bounds = draftBounds[dragState.annotation.id];
    setDragState(null);
    if (!bounds) {
      return;
    }
    await onUpdateSegment(dragState.annotation.id, {
      labelType: dragState.annotation.labelType,
      labelValue: dragState.annotation.labelValue,
      startFrame: bounds.startFrame,
      endFrame: bounds.endFrame
    });
  }

  return (
    <section className="timeline-panel">
      <div className="timeline-toolbar">
        <div>
          <div className="section-title">Timeline</div>
          <div className="muted">Frame {activeFrame}</div>
        </div>
        <div className="timeline-actions">
          <button className="text-button compact-text-button" onClick={handleCreateMarker} type="button">
            <MapPin size={14} />
            Marker
          </button>
          <button className="text-button compact-text-button" onClick={handleCreateBadRange} type="button">
            <OctagonAlert size={14} />
            Bad range
          </button>
        </div>
      </div>
      <div className="timeline-ruler">
        {rulerValues.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
      <div
        className="timeline-track"
        onPointerDown={handleTrackPointerDown}
        onPointerLeave={handleDragPointerUp}
        onPointerMove={handleDragPointerMove}
        onPointerUp={handleDragPointerUp}
        ref={trackRef}
      >
        <div
          className="timeline-selected-frame"
          style={{ left: `${framePercent(activeFrame, safeFrameCount)}%` }}
        />
        {sortedAnnotations.map((annotation, index) => {
          const nextAnnotation = sortedAnnotations[index + 1] ?? null;
          const bounds = draftBounds[annotation.id] ?? {
            startFrame: annotation.startFrame,
            endFrame: annotation.endFrame
          };
          const left = framePercent(bounds.startFrame, safeFrameCount);
          const width = Math.max(
            0.8,
            ((bounds.endFrame - bounds.startFrame + 1) / safeFrameCount) * 100
          );
          return (
            <div
              className={`timeline-segment segment-${annotation.reviewStatus} label-${annotation.labelType}`}
              key={annotation.id}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`${annotation.labelValue} (${bounds.startFrame}-${bounds.endFrame})`}
            >
              <button
                aria-label="Drag segment start"
                className="timeline-handle left"
                onPointerDown={(event) => {
                  event.stopPropagation();
                  setDragState({ annotation, edge: "start" });
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                type="button"
              />
              <button
                className="timeline-segment-body"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectFrame(bounds.startFrame);
                }}
                type="button"
              >
                {annotation.labelValue}
              </button>
              <span className="timeline-segment-controls">
                <button
                  aria-label="Split segment"
                  disabled={annotation.endFrame <= annotation.startFrame}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onSplitSegment(annotation);
                  }}
                  type="button"
                >
                  <GitBranch size={12} />
                </button>
                <button
                  aria-label="Merge with next segment"
                  disabled={nextAnnotation === null}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (nextAnnotation !== null) {
                      void onMergeSegments(annotation, nextAnnotation);
                    }
                  }}
                  type="button"
                >
                  <Merge size={12} />
                </button>
                <button
                  aria-label="Delete segment"
                  onClick={(event) => {
                    event.stopPropagation();
                    void onDeleteSegment(annotation.id);
                  }}
                  type="button"
                >
                  <Trash2 size={12} />
                </button>
              </span>
              <button
                aria-label="Drag segment end"
                className="timeline-handle right"
                onPointerDown={(event) => {
                  event.stopPropagation();
                  setDragState({ annotation, edge: "end" });
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                type="button"
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}

function framePercent(frame: number, frameCount: number): number {
  return (frame / Math.max(1, frameCount - 1)) * 100;
}

function clampFrame(frame: number, maxFrame: number): number {
  return Math.max(0, Math.min(maxFrame, Math.round(frame)));
}

function frameFromPointer(
  event: ReactPointerEvent<HTMLElement>,
  track: HTMLDivElement | null,
  maxFrame: number,
): number {
  if (track === null) {
    return 0;
  }
  const rect = track.getBoundingClientRect();
  const ratio = rect.width <= 0 ? 0 : (event.clientX - rect.left) / rect.width;
  return clampFrame(ratio * maxFrame, maxFrame);
}
