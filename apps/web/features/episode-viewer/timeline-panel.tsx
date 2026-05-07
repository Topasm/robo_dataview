import { AlertTriangle, GitBranch, MapPin, Merge, OctagonAlert, Trash2 } from "lucide-react";
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { findClipOverlaps, type ClipOverlap } from "@/lib/clip-validation";
import { SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type { SegmentAnnotation } from "@/lib/types";

type SegmentDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
  metadata?: SegmentAnnotation["metadata"];
};

type TimelinePanelProps = {
  annotations: SegmentAnnotation[];
  clipEnd?: number | null;
  clipStart?: number | null;
  fps?: number;
  frameCount: number;
  onCreateSegment: (draft: SegmentDraft) => Promise<void>;
  onDeleteSegment: (annotationId: string) => Promise<void>;
  onMergeSegments: (left: SegmentAnnotation, right: SegmentAnnotation) => Promise<void>;
  onSelectFrame: (frameIndex: number) => void;
  onSelectSegment?: (annotationId: string | null) => void;
  onSetClipEnd?: (frame: number | null) => void;
  onSetClipStart?: (frame: number | null) => void;
  onSplitSegment: (annotation: SegmentAnnotation) => Promise<void>;
  onUpdateSegment: (annotationId: string, draft: SegmentDraft) => Promise<void>;
  selectedSegmentId?: string | null;
  selectedFrame: number;
};

type DragState = {
  annotation: SegmentAnnotation;
  edge: "start" | "end";
  laneKey: string;
};

type TimelineLane = {
  key: string;
  title: string;
  annotations: SegmentAnnotation[];
};

export function TimelinePanel({
  annotations,
  fps = 20,
  frameCount,
  onCreateSegment,
  onDeleteSegment,
  onMergeSegments,
  onSelectFrame,
  onSelectSegment,
  onSetClipEnd,
  onSetClipStart,
  onSplitSegment,
  onUpdateSegment,
  selectedSegmentId = null,
  selectedFrame
}: TimelinePanelProps) {
  const trackRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [draftBounds, setDraftBounds] = useState<Record<string, { startFrame: number; endFrame: number }>>({});
  const safeFrameCount = Math.max(1, frameCount);
  const maxFrame = Math.max(0, safeFrameCount - 1);
  const activeFrame = clampFrame(selectedFrame, maxFrame);
  const sortedAnnotations = useMemo(
    () => [...annotations].sort((left, right) => left.startFrame - right.startFrame),
    [annotations]
  );
  const timelineLanes = useMemo<TimelineLane[]>(
    () => [
      {
        key: "skills",
        title: "Skill Clips",
        annotations: sortedAnnotations.filter((annotation) => annotation.labelType === SKILL_LABEL_TYPE)
      },
      {
        key: "bad",
        title: "Bad Ranges",
        annotations: sortedAnnotations.filter((annotation) => annotation.labelType === "bad_range")
      },
      {
        key: "events",
        title: "Events",
        annotations: sortedAnnotations.filter(
          (annotation) => annotation.labelType !== SKILL_LABEL_TYPE && annotation.labelType !== "bad_range"
        )
      }
    ],
    [sortedAnnotations]
  );

  const rulerValues = useMemo(
    () => [0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round(maxFrame * ratio)),
    [maxFrame]
  );
  const overlapsMap = useMemo(() => findClipOverlaps(annotations), [annotations]);

  async function handleCreateMarker() {
    await onCreateSegment({
      labelType: "important_frame",
      labelValue: "important_frame",
      startFrame: activeFrame,
      endFrame: activeFrame
    });
  }

  function rangeAroundActiveFrame(seconds: number) {
    const radius = Math.max(1, Math.round((fps * seconds) / 2));
    return {
      startFrame: clampFrame(activeFrame - radius, maxFrame),
      endFrame: clampFrame(activeFrame + radius, maxFrame)
    };
  }

  async function handleCreateBadRange(seconds = 1) {
    const { startFrame, endFrame } = rangeAroundActiveFrame(seconds);
    await onCreateSegment({
      labelType: "bad_range",
      labelValue: `bad_${seconds}s`,
      startFrame,
      endFrame
    });
  }

  async function handleCreateEvent(type: string) {
    await onCreateSegment({
      labelType: type,
      labelValue: type,
      startFrame: activeFrame,
      endFrame: activeFrame
    });
  }

  function handleTrackPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) {
      return;
    }
    onSelectFrame(frameFromPointer(event, event.currentTarget, maxFrame));
  }

  function handleDragPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragState === null) {
      return;
    }
    const frame = frameFromPointer(event, trackRefs.current[dragState.laneKey] ?? null, maxFrame);
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
          <button className="text-button compact-text-button" onClick={() => void handleCreateBadRange(0.5)} type="button">
            <OctagonAlert size={14} />
            Bad ±0.5s
          </button>
          <button className="text-button compact-text-button" onClick={() => void handleCreateBadRange(1)} type="button">
            <OctagonAlert size={14} />
            Bad ±1s
          </button>
          <button className="text-button compact-text-button" onClick={() => void handleCreateEvent("foot_slip")} type="button">
            Slip
          </button>
          <button className="text-button compact-text-button" onClick={() => void handleCreateEvent("fall_event")} type="button">
            Fall
          </button>
          <button className="text-button compact-text-button" onClick={() => void handleCreateEvent("collision")} type="button">
            Collision
          </button>
          {onSetClipStart ? (
            <button className="text-button compact-text-button" onClick={() => onSetClipStart(activeFrame)} type="button" style={{ background: "#e4f5ed", borderColor: "#acd8c1" }}>
              Set Start
            </button>
          ) : null}
          {onSetClipEnd ? (
            <button className="text-button compact-text-button" onClick={() => onSetClipEnd(activeFrame)} type="button" style={{ background: "#e7effb", borderColor: "#b7c9ea" }}>
              Set End
            </button>
          ) : null}
        </div>
      </div>
      <div className="timeline-ruler">
        {rulerValues.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
      <div className="timeline-lanes">
        {timelineLanes.map((lane) => (
          <div className="timeline-lane" key={lane.key}>
            <div className="timeline-lane-title">{lane.title}</div>
            <div
              className="timeline-track"
              onPointerDown={handleTrackPointerDown}
              onPointerLeave={handleDragPointerUp}
              onPointerMove={handleDragPointerMove}
              onPointerUp={handleDragPointerUp}
              ref={(node) => {
                trackRefs.current[lane.key] = node;
              }}
            >
              <div
                className="timeline-selected-frame"
                style={{ left: `${framePercent(activeFrame, safeFrameCount)}%` }}
              />
              {lane.annotations.map((annotation, index) => {
                const nextAnnotation = lane.annotations[index + 1] ?? null;
                const mergeAllowed = canMerge(annotation, nextAnnotation);
                const bounds = draftBounds[annotation.id] ?? {
                  startFrame: annotation.startFrame,
                  endFrame: annotation.endFrame
                };
                const left = framePercent(bounds.startFrame, safeFrameCount);
                const width = Math.max(
                  0.8,
                  ((bounds.endFrame - bounds.startFrame + 1) / safeFrameCount) * 100
                );
                const overlaps = overlapsMap.get(annotation.id) ?? [];
                const hasOverlap = overlaps.length > 0;
                const baseTitle = `${annotation.labelValue} (${bounds.startFrame}-${bounds.endFrame})`;
                const segmentTitle = hasOverlap
                  ? `${baseTitle}\n${formatOverlapTooltip(overlaps)}`
                  : baseTitle;
                const segmentClassName = [
                  "timeline-segment",
                  `segment-${annotation.reviewStatus}`,
                  `label-${annotation.labelType}`,
                  hasOverlap ? "has-overlap" : null,
                  selectedSegmentId === annotation.id ? "selected" : null
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <div
                    className={segmentClassName}
                    key={annotation.id}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={segmentTitle}
                  >
                    <button
                      aria-label="Drag segment start"
                      className="timeline-handle left"
                      onPointerDown={(event) => {
                        event.stopPropagation();
                        setDragState({ annotation, edge: "start", laneKey: lane.key });
                        event.currentTarget.setPointerCapture(event.pointerId);
                      }}
                      type="button"
                    />
                    <button
                      className="timeline-segment-body"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (annotation.labelType === SKILL_LABEL_TYPE) {
                          onSelectSegment?.(annotation.id);
                        }
                        onSelectFrame(bounds.startFrame);
                      }}
                      type="button"
                    >
                      {annotation.labelValue}
                    </button>
                    {hasOverlap ? (
                      <span className="timeline-overlap-warning" aria-hidden="true">
                        <AlertTriangle size={11} />
                      </span>
                    ) : null}
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
                        disabled={!mergeAllowed}
                        onClick={(event) => {
                          event.stopPropagation();
                          if (mergeAllowed) {
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
                        setDragState({ annotation, edge: "end", laneKey: lane.key });
                        event.currentTarget.setPointerCapture(event.pointerId);
                      }}
                      type="button"
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatOverlapTooltip(overlaps: ClipOverlap[]): string {
  if (overlaps.length === 0) {
    return "";
  }
  const summary = overlaps
    .map((overlap) => `${overlap.otherSkill} f${overlap.otherStart}-f${overlap.otherEnd}`)
    .join(", ");
  if (overlaps.length === 1) {
    return `Overlaps with ${summary}`;
  }
  return `Overlaps with ${overlaps.length} clips: ${summary}`;
}

function canMerge(left: SegmentAnnotation, right: SegmentAnnotation | null): right is SegmentAnnotation {
  if (right === null) {
    return false;
  }
  if (left.labelType !== right.labelType) {
    return false;
  }
  if (left.labelType === SKILL_LABEL_TYPE) {
    return left.labelValue === right.labelValue;
  }
  return true;
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
