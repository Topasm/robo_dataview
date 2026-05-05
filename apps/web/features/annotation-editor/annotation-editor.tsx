import { useEffect, useState } from "react";
import { Bot, Check, GitBranch, Minus, Plus, Save, Trash2, X } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { FrameMetadataPanel } from "@/features/episode-viewer/frame-metadata-panel";
import { FrameTablePanel } from "@/features/episode-viewer/frame-table-panel";
import type {
  Episode,
  FrameListPage,
  FrameRecord,
  JobRecord,
  ReviewStatus,
  AnnotationHistoryRecord,
  SegmentAnnotation
} from "@/lib/types";

type AnnotationDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
};

type EpisodeLabelDraft = {
  caption: string;
  successLabel: boolean | null;
  failureReason: string;
  qualityScore: number | null;
  split: string | null;
  reviewStatus: ReviewStatus;
};

type AnnotationEditorProps = {
  episode: Episode;
  annotationHistory: AnnotationHistoryRecord[];
  annotations: SegmentAnnotation[];
  frameBrowserLimit: number;
  frameBrowserStart: number;
  framePage: FrameListPage | null;
  frameRows: FrameRecord[];
  frameRowsStatus: "idle" | "loading" | "ready" | "error";
  selectedFrame: number;
  selectedFrameRecord: FrameRecord | null;
  selectedFrameStatus: "idle" | "loading" | "ready" | "error";
  vlmJob: JobRecord | null;
  onCreateSegment: (draft: AnnotationDraft) => Promise<void>;
  onDeleteSegment: (annotationId: string) => Promise<void>;
  onRunVlmLabel: () => Promise<void>;
  onSplitSegment: (annotation: SegmentAnnotation) => Promise<void>;
  onUpdateEpisodeLabels: (draft: EpisodeLabelDraft) => Promise<void>;
  onSetFrameBrowserLimit: (limit: number) => void;
  onSetFrameBrowserStart: (startFrame: number) => void;
  onUpdateFrameBadFlag: (frameIndex: number, isBadFrame: boolean) => Promise<void>;
  onUpdateSelectedFrameLabel: (
    labelType: string,
    labelValue: string,
    labelEnabled: boolean,
  ) => Promise<void>;
  onUpdateSelectedFrameBadFlag: (isBadFrame: boolean) => Promise<void>;
  onUpdateSegment: (annotationId: string, draft: AnnotationDraft) => Promise<void>;
  onUpdateReviewStatus: (annotationId: string, status: ReviewStatus) => Promise<void>;
  onSelectFrame: (frameIndex: number) => void;
};

export function AnnotationEditor({
  episode,
  annotationHistory,
  annotations,
  frameBrowserLimit,
  frameBrowserStart,
  framePage,
  frameRows,
  frameRowsStatus,
  selectedFrame,
  selectedFrameRecord,
  selectedFrameStatus,
  vlmJob,
  onCreateSegment,
  onDeleteSegment,
  onRunVlmLabel,
  onSplitSegment,
  onUpdateEpisodeLabels,
  onSetFrameBrowserLimit,
  onSetFrameBrowserStart,
  onUpdateFrameBadFlag,
  onUpdateSelectedFrameLabel,
  onUpdateSelectedFrameBadFlag,
  onUpdateSegment,
  onUpdateReviewStatus,
  onSelectFrame
}: AnnotationEditorProps) {
  const [episodeDraft, setEpisodeDraft] = useState<EpisodeLabelDraft>(() => toEpisodeDraft(episode));
  const [draft, setDraft] = useState<AnnotationDraft>({
    labelType: "phase",
    labelValue: "phase_label",
    startFrame: 0,
    endFrame: Math.max(0, Math.min(episode.length - 1, 30))
  });
  const [editingRows, setEditingRows] = useState<Record<string, AnnotationDraft>>({});
  const [isSavingEpisode, setIsSavingEpisode] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRunningVlm, setIsRunningVlm] = useState(false);
  const generatedProposals = annotations
    .filter(
      (annotation) =>
        (annotation.source === "vlm" || annotation.source === "heuristic") &&
        annotation.reviewStatus === "pending"
    )
    .sort((left, right) => left.startFrame - right.startFrame);
  const isVlmJobActive = vlmJob ? !["succeeded", "failed"].includes(vlmJob.status) : false;
  const vlmProgressPercent = Math.round(Math.max(0, Math.min(1, vlmJob?.progress ?? 0)) * 100);
  const recentHistory = [...annotationHistory]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
    .slice(0, 8);

  useEffect(() => {
    setEpisodeDraft(toEpisodeDraft(episode));
    setDraft((current) => ({
      ...current,
      endFrame: Math.max(0, Math.min(episode.length - 1, current.endFrame))
    }));
  }, [episode]);

  async function handleUpdateEpisodeLabels() {
    setIsSavingEpisode(true);
    try {
      await onUpdateEpisodeLabels(episodeDraft);
    } finally {
      setIsSavingEpisode(false);
    }
  }

  async function handleCreateSegment() {
    if (!draft.labelValue.trim()) {
      return;
    }
    setIsSaving(true);
    try {
      await onCreateSegment({
        ...draft,
        labelValue: draft.labelValue.trim()
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleUpdateSegment(annotation: SegmentAnnotation) {
    const edit = editingRows[annotation.id] ?? toDraft(annotation);
    if (!edit.labelValue.trim()) {
      return;
    }
    setIsSaving(true);
    try {
      await onUpdateSegment(annotation.id, {
        ...edit,
        labelValue: edit.labelValue.trim()
      });
      setEditingRows((current) => {
        const next = { ...current };
        delete next[annotation.id];
        return next;
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSplitSegment(annotation: SegmentAnnotation) {
    setIsSaving(true);
    try {
      await onSplitSegment(annotation);
    } finally {
      setIsSaving(false);
    }
  }

  function updateRowDraft(annotation: SegmentAnnotation, patch: Partial<AnnotationDraft>) {
    setEditingRows((current) => ({
      ...current,
      [annotation.id]: {
        ...(current[annotation.id] ?? toDraft(annotation)),
        ...patch
      }
    }));
  }

  async function handleRunVlmLabel() {
    setIsRunningVlm(true);
    try {
      await onRunVlmLabel();
    } finally {
      setIsRunningVlm(false);
    }
  }

  return (
    <aside className="right-panel">
      <section className="panel-section">
        <div className="section-title">Episode Labels</div>
        <div className="form-grid">
          <label>
            Caption
            <textarea
              onChange={(event) =>
                setEpisodeDraft((current) => ({ ...current, caption: event.target.value }))
              }
              rows={3}
              value={episodeDraft.caption}
            />
          </label>
          <label>
            Quality
            <input
              max={1}
              min={0}
              onChange={(event) =>
                setEpisodeDraft((current) => ({
                  ...current,
                  qualityScore: event.target.value === "" ? null : Number(event.target.value)
                }))
              }
              placeholder="unset"
              step={0.01}
              type="number"
              value={episodeDraft.qualityScore ?? ""}
            />
          </label>
          <label>
            Split
            <select
              onChange={(event) =>
                setEpisodeDraft((current) => ({
                  ...current,
                  split: event.target.value === "" ? null : event.target.value
                }))
              }
              value={episodeDraft.split ?? ""}
            >
              <option value="">unassigned</option>
              <option value="train">train</option>
              <option value="val">val</option>
              <option value="test">test</option>
            </select>
          </label>
          <label>
            Review
            <select
              onChange={(event) =>
                setEpisodeDraft((current) => ({
                  ...current,
                  reviewStatus: event.target.value as ReviewStatus
                }))
              }
              value={episodeDraft.reviewStatus}
            >
              <option value="pending">pending</option>
              <option value="accepted">accepted</option>
              <option value="rejected">rejected</option>
              <option value="edited">edited</option>
            </select>
          </label>
          <label>
            Failure reason
            <textarea
              onChange={(event) =>
                setEpisodeDraft((current) => ({ ...current, failureReason: event.target.value }))
              }
              rows={2}
              value={episodeDraft.failureReason}
            />
          </label>
        </div>
        <div className="segmented-control">
          <button
            className={episodeDraft.successLabel === null ? "active" : ""}
            onClick={() => setEpisodeDraft((current) => ({ ...current, successLabel: null }))}
            type="button"
          >
            <Minus size={14} />
            Unknown
          </button>
          <button
            className={episodeDraft.successLabel === true ? "active" : ""}
            onClick={() => setEpisodeDraft((current) => ({ ...current, successLabel: true }))}
            type="button"
          >
            <Check size={14} />
            Success
          </button>
          <button
            className={episodeDraft.successLabel === false ? "active" : ""}
            onClick={() => setEpisodeDraft((current) => ({ ...current, successLabel: false }))}
            type="button"
          >
            <X size={14} />
            Failure
          </button>
        </div>
        <button
          className="text-button episode-label-save"
          disabled={isSavingEpisode}
          onClick={handleUpdateEpisodeLabels}
          type="button"
        >
          <Save size={15} />
          Save labels
        </button>
      </section>

      <FrameMetadataPanel
        frame={selectedFrameRecord}
        onSetBadFrame={onUpdateSelectedFrameBadFlag}
        onSetFrameLabel={onUpdateSelectedFrameLabel}
        selectedFrame={selectedFrame}
        status={selectedFrameStatus}
      />

      <FrameTablePanel
        frameCount={framePage?.frameCount ?? episode.length}
        frameLimit={frameBrowserLimit}
        frameStart={frameBrowserStart}
        frames={frameRows}
        onFrameLimitChange={onSetFrameBrowserLimit}
        onFrameStartChange={onSetFrameBrowserStart}
        onSelectFrame={onSelectFrame}
        onSetBadFrame={onUpdateFrameBadFlag}
        returnedCount={framePage?.returnedCount ?? frameRows.length}
        selectedFrame={selectedFrame}
        status={frameRowsStatus}
      />

      <section className="panel-section">
        <div className="section-title">VLM Proposals</div>
        <button
          className="text-button vlm-run-button"
          disabled={isRunningVlm || isVlmJobActive}
          onClick={handleRunVlmLabel}
          type="button"
        >
          <Bot size={15} />
          Run VLM
        </button>
        {vlmJob ? (
          <div className="vlm-job-status">
            <StatusPill status={vlmJob.status} />
            <span className="muted">{vlmJob.message}</span>
            <span className="mono">
              {vlmJob.promptTemplate}
              {vlmJob.promptVersion ? `@${vlmJob.promptVersion}` : ""}
            </span>
            {vlmJob.provider ? <span className="mono">{vlmJob.provider}</span> : null}
            {vlmJob.rawResponseIds.length > 0 ? (
              <span className="mono">{vlmJob.rawResponseIds.length} raw</span>
            ) : null}
            {vlmJob.queueJobId ? <span className="mono">queue {vlmJob.queueJobId}</span> : null}
            <div className="vlm-progress">
              <div className="progress-track compact-progress-track">
                <div className="progress-fill" style={{ width: `${vlmProgressPercent}%` }} />
              </div>
              <span className="mono">{vlmProgressPercent}%</span>
            </div>
          </div>
        ) : null}
        <div className="proposal-list">
          {generatedProposals.length === 0 ? (
            <div className="empty-state compact-empty-state">No pending generated labels.</div>
          ) : (
            generatedProposals.map((annotation) => (
              <div className="proposal-row" key={annotation.id}>
                <div className="proposal-body">
                  <div className="proposal-label">{annotation.labelValue}</div>
                  <div className="muted mono">
                    {annotation.labelType} / f{annotation.startFrame}-{annotation.endFrame} /{" "}
                    {annotation.confidence.toFixed(2)}
                  </div>
                </div>
                <div className="proposal-actions">
                  <button
                    className="icon-button compact"
                    onClick={() => onUpdateReviewStatus(annotation.id, "accepted")}
                    title="Accept generated label"
                    type="button"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    className="icon-button compact"
                    onClick={() => onUpdateReviewStatus(annotation.id, "rejected")}
                    title="Reject generated label"
                    type="button"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">New Segment</div>
        <div className="segment-form">
          <label>
            Type
            <select
              onChange={(event) => setDraft((current) => ({ ...current, labelType: event.target.value }))}
              value={draft.labelType}
            >
              <option value="phase">phase</option>
              <option value="bad_range">bad_range</option>
              <option value="important_frame">important_frame</option>
              <option value="failure_event">failure_event</option>
            </select>
          </label>
          <label>
            Phase
            <input
              onChange={(event) => setDraft((current) => ({ ...current, labelValue: event.target.value }))}
              value={draft.labelValue}
            />
          </label>
          <label>
            Start
            <input
              min={0}
              onChange={(event) =>
                setDraft((current) => ({ ...current, startFrame: Number(event.target.value) }))
              }
              type="number"
              value={draft.startFrame}
            />
          </label>
          <label>
            End
            <input
              min={0}
              onChange={(event) =>
                setDraft((current) => ({ ...current, endFrame: Number(event.target.value) }))
              }
              type="number"
              value={draft.endFrame}
            />
          </label>
          <button
            className="text-button segment-save-button"
            disabled={isSaving}
            onClick={handleCreateSegment}
            type="button"
          >
            <Plus size={15} />
            Add
          </button>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">Segments</div>
        <div className="segment-list">
          {annotations.length === 0 ? <div className="empty-state">No annotations for this episode.</div> : null}
          {annotations.map((annotation) => (
            <div className="segment-row" key={annotation.id}>
              <div className="segment-edit-grid">
                <input
                  aria-label="Segment label"
                  onChange={(event) => updateRowDraft(annotation, { labelValue: event.target.value })}
                  value={(editingRows[annotation.id] ?? toDraft(annotation)).labelValue}
                />
                <select
                  aria-label="Segment type"
                  onChange={(event) => updateRowDraft(annotation, { labelType: event.target.value })}
                  value={(editingRows[annotation.id] ?? toDraft(annotation)).labelType}
                >
                  <option value="phase">phase</option>
                  <option value="bad_range">bad_range</option>
                  <option value="important_frame">important_frame</option>
                  <option value="failure_event">failure_event</option>
                  <option value="episode_caption">episode_caption</option>
                  <option value="success_label">success_label</option>
                </select>
                <input
                  aria-label="Start frame"
                  min={0}
                  onChange={(event) => updateRowDraft(annotation, { startFrame: Number(event.target.value) })}
                  type="number"
                  value={(editingRows[annotation.id] ?? toDraft(annotation)).startFrame}
                />
                <input
                  aria-label="End frame"
                  min={0}
                  onChange={(event) => updateRowDraft(annotation, { endFrame: Number(event.target.value) })}
                  type="number"
                  value={(editingRows[annotation.id] ?? toDraft(annotation)).endFrame}
                />
                <div className="muted mono">
                  {annotation.source} / {annotation.confidence.toFixed(2)}
                </div>
              </div>
              <StatusPill status={annotation.reviewStatus} />
              <div className="segment-actions">
                <button
                  className="icon-button compact"
                  disabled={isSaving}
                  onClick={() => handleUpdateSegment(annotation)}
                  title="Save segment edits"
                  type="button"
                >
                  <Save size={14} />
                </button>
                <button
                  className="icon-button compact"
                  disabled={isSaving || annotation.endFrame <= annotation.startFrame}
                  onClick={() => handleSplitSegment(annotation)}
                  title="Split segment at midpoint"
                  type="button"
                >
                  <GitBranch size={14} />
                </button>
                <button
                  className="icon-button compact"
                  onClick={() => onUpdateReviewStatus(annotation.id, "accepted")}
                  title="Accept segment"
                  type="button"
                >
                  <Check size={14} />
                </button>
                <button
                  className="icon-button compact"
                  onClick={() => onUpdateReviewStatus(annotation.id, "rejected")}
                  title="Reject segment"
                  type="button"
                >
                  <X size={14} />
                </button>
                <button
                  className="icon-button compact danger"
                  onClick={() => onDeleteSegment(annotation.id)}
                  title="Delete segment"
                  type="button"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">History</div>
        <div className="history-list">
          {recentHistory.length === 0 ? (
            <div className="empty-state compact-empty-state">No annotation history.</div>
          ) : (
            recentHistory.map((event) => (
              <div className="history-row" key={event.eventId}>
                <div className="history-row-top">
                  <span className={`history-action history-action-${event.action}`}>
                    {event.action}
                  </span>
                  <span className="muted">{formatHistoryTime(event.createdAt)}</span>
                </div>
                <div className="history-label">{historyLabel(event)}</div>
                <div className="muted mono">
                  {event.actor} / {historyFrameRange(event)}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}

function toEpisodeDraft(episode: Episode): EpisodeLabelDraft {
  return {
    caption: episode.caption,
    successLabel: episode.successLabel,
    failureReason: episode.failureReason,
    qualityScore: episode.qualityScore,
    split: episode.split,
    reviewStatus: episode.reviewStatus
  };
}

function toDraft(annotation: SegmentAnnotation): AnnotationDraft {
  return {
    labelType: annotation.labelType,
    labelValue: annotation.labelValue,
    startFrame: annotation.startFrame,
    endFrame: annotation.endFrame
  };
}

function historyPayload(event: AnnotationHistoryRecord): Record<string, unknown> | null {
  return event.after ?? event.before;
}

function historyLabel(event: AnnotationHistoryRecord): string {
  const payload = historyPayload(event);
  const labelType = stringField(payload, "label_type");
  const labelValue = stringField(payload, "label_value");
  if (labelType && labelValue) {
    return `${labelType}: ${labelValue}`;
  }
  return event.annotationId;
}

function historyFrameRange(event: AnnotationHistoryRecord): string {
  const payload = historyPayload(event);
  const startFrame = numberField(payload, "start_frame");
  const endFrame = numberField(payload, "end_frame");
  if (startFrame === null || endFrame === null) {
    return `episode ${event.episodeIndex}`;
  }
  return `f${startFrame}-${endFrame}`;
}

function stringField(payload: Record<string, unknown> | null, key: string): string | null {
  const value = payload?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberField(payload: Record<string, unknown> | null, key: string): number | null {
  const value = payload?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatHistoryTime(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric"
  }).format(timestamp);
}
