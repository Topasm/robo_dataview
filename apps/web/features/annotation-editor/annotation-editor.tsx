import { useEffect, useMemo, useState } from "react";
import { Bot, Check, GitBranch, Minus, Plus, Save, Trash2, UserCheck, UserX, X } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { FrameMetadataPanel } from "@/features/episode-viewer/frame-metadata-panel";
import { FrameTablePanel } from "@/features/episode-viewer/frame-table-panel";
import type {
  Episode,
  EpisodeLabelHistoryRecord,
  FrameListPage,
  FrameRecord,
  JobRecord,
  ReviewStatus,
  AnnotationHistoryRecord,
  SegmentAnnotation,
  VlmResponseRecord
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
  episodeLabelHistory: EpisodeLabelHistoryRecord[];
  annotations: SegmentAnnotation[];
  frameBrowserLimit: number;
  frameBrowserStart: number;
  framePage: FrameListPage | null;
  frameRows: FrameRecord[];
  frameRowsStatus: "idle" | "loading" | "ready" | "error";
  selectedFrame: number;
  selectedFrameRecord: FrameRecord | null;
  selectedFrameStatus: "idle" | "loading" | "ready" | "error";
  reviewerUserId: string;
  vlmJob: JobRecord | null;
  vlmResponses: VlmResponseRecord[];
  onAssignAnnotation: (annotationId: string, assignedTo: string | null) => Promise<void>;
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
  episodeLabelHistory,
  annotations,
  frameBrowserLimit,
  frameBrowserStart,
  framePage,
  frameRows,
  frameRowsStatus,
  selectedFrame,
  selectedFrameRecord,
  selectedFrameStatus,
  reviewerUserId,
  vlmJob,
  vlmResponses,
  onAssignAnnotation,
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
  const [isBulkReviewing, setIsBulkReviewing] = useState(false);
  const [isRunningVlm, setIsRunningVlm] = useState(false);
  const generatedProposals = annotations
    .filter(
      (annotation) =>
        (annotation.source === "vlm" || annotation.source === "heuristic") &&
        annotation.reviewStatus === "pending"
    )
    .sort((left, right) => left.startFrame - right.startFrame);
  const pendingAnnotations = annotations.filter((annotation) => annotation.reviewStatus === "pending");
  const claimablePendingAnnotations = pendingAnnotations.filter(
    (annotation) => annotation.assignedTo !== reviewerUserId
  );
  const assignedAnnotations = annotations.filter((annotation) => annotation.assignedTo !== null);
  const isVlmJobActive = vlmJob ? !["succeeded", "failed"].includes(vlmJob.status) : false;
  const vlmProgressPercent = Math.round(Math.max(0, Math.min(1, vlmJob?.progress ?? 0)) * 100);
  const recentHistory = [...annotationHistory]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
    .slice(0, 8);
  const recentLabelHistory = [...episodeLabelHistory]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
    .slice(0, 8);
  const rationaleRows = vlmResponses.flatMap(responseRationaleRows).slice(0, 6);
  const subtaskSummary = useMemo(
    () => computeSubtaskSummary(annotations, episode.length),
    [annotations, episode.length]
  );

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

  async function handleBulkReview(rows: SegmentAnnotation[], status: ReviewStatus) {
    if (rows.length === 0) {
      return;
    }
    setIsBulkReviewing(true);
    try {
      for (const annotation of rows) {
        await onUpdateReviewStatus(annotation.id, status);
      }
    } finally {
      setIsBulkReviewing(false);
    }
  }

  async function handleClaimPending() {
    if (claimablePendingAnnotations.length === 0) {
      return;
    }
    setIsBulkReviewing(true);
    try {
      for (const annotation of claimablePendingAnnotations) {
        await onAssignAnnotation(annotation.id, reviewerUserId);
      }
    } finally {
      setIsBulkReviewing(false);
    }
  }

  async function handleClearAssignments() {
    if (assignedAnnotations.length === 0) {
      return;
    }
    setIsBulkReviewing(true);
    try {
      for (const annotation of assignedAnnotations) {
        await onAssignAnnotation(annotation.id, null);
      }
    } finally {
      setIsBulkReviewing(false);
    }
  }

  async function handleApplyGeneratedProposal(annotation: SegmentAnnotation) {
    const nextDraft = episodeDraftFromProposal(episodeDraft, annotation);
    if (nextDraft === null) {
      return;
    }
    setEpisodeDraft(nextDraft);
    setIsSavingEpisode(true);
    try {
      await onUpdateEpisodeLabels(nextDraft);
      await onUpdateReviewStatus(annotation.id, "accepted");
    } finally {
      setIsSavingEpisode(false);
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
        <div className="section-title">Subtask Coverage</div>
        <div className="subtask-summary-grid">
          <div className="metric compact-metric">
            <span>Coverage</span>
            <strong>{subtaskSummary.coveragePercent.toFixed(0)}%</strong>
          </div>
          <div className="metric compact-metric">
            <span>Gaps</span>
            <strong>{subtaskSummary.gapCount}</strong>
          </div>
          <div className="metric compact-metric">
            <span>Overlap</span>
            <strong>{subtaskSummary.overlapCount}</strong>
          </div>
        </div>
        <div className="subtask-bar" aria-label="Subtask timeline coverage">
          {subtaskSummary.rows.map((row) => (
            <span
              className={`subtask-bar-segment subtask-${row.reviewStatus}`}
              key={row.id}
              style={{ left: `${row.leftPercent}%`, width: `${row.widthPercent}%` }}
              title={`${row.label} f${row.startFrame}-${row.endFrame}`}
            />
          ))}
        </div>
        <div className="subtask-list">
          {subtaskSummary.rows.length === 0 ? (
            <div className="empty-state compact-empty-state">No phase or subtask annotations.</div>
          ) : (
            subtaskSummary.rows.slice(0, 6).map((row) => (
              <div className="subtask-row" key={row.id}>
                <span className="subtask-label">{row.label}</span>
                <span className="muted mono">
                  {row.kind} / {row.percent.toFixed(0)}% / f{row.startFrame}-{row.endFrame}
                </span>
              </div>
            ))
          )}
        </div>
      </section>

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
        {rationaleRows.length > 0 ? (
          <div className="rationale-list">
            {rationaleRows.map((row) => (
              <div className="rationale-row" key={row.id}>
                <div className="rationale-label">
                  <span>{row.label}</span>
                  {row.confidence !== null ? (
                    <span className="mono">{row.confidence.toFixed(2)}</span>
                  ) : null}
                </div>
                {row.rationale ? <div className="muted">{row.rationale}</div> : null}
              </div>
            ))}
          </div>
        ) : null}
        {generatedProposals.length > 0 ? (
          <div className="review-action-grid">
            <button
              className="text-button compact-text-button"
              disabled={isBulkReviewing}
              onClick={() => void handleBulkReview(generatedProposals, "accepted")}
              type="button"
            >
              <Check size={14} />
              Accept all
            </button>
            <button
              className="text-button compact-text-button"
              disabled={isBulkReviewing}
              onClick={() => void handleBulkReview(generatedProposals, "rejected")}
              type="button"
            >
              <X size={14} />
              Reject all
            </button>
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
                  {episodeDraftFromProposal(episodeDraft, annotation) !== null ? (
                    <button
                      className="icon-button compact"
                      onClick={() => void handleApplyGeneratedProposal(annotation)}
                      title="Apply to episode labels and accept"
                      type="button"
                    >
                      <Save size={14} />
                    </button>
                  ) : null}
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
              <option value="subtask">subtask</option>
              <option value="bad_range">bad_range</option>
              <option value="important_frame">important_frame</option>
              <option value="failure_event">failure_event</option>
            </select>
          </label>
          <label>
            Label
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
        <div className="review-action-grid">
          <button
            className="text-button compact-text-button"
            disabled={isBulkReviewing || claimablePendingAnnotations.length === 0}
            onClick={() => void handleClaimPending()}
            type="button"
          >
            <UserCheck size={14} />
            Claim pending
          </button>
          <button
            className="text-button compact-text-button"
            disabled={isBulkReviewing || assignedAnnotations.length === 0}
            onClick={() => void handleClearAssignments()}
            type="button"
          >
            <UserX size={14} />
            Clear assigned
          </button>
        </div>
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
                  <option value="subtask">subtask</option>
                  <option value="bad_range">bad_range</option>
                  <option value="important_frame">important_frame</option>
                  <option value="failure_event">failure_event</option>
                  <option value="episode_caption">episode_caption</option>
                  <option value="success_label">success_label</option>
                  <option value="failure_reason">failure_reason</option>
                  <option value="object_list">object_list</option>
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
                  {annotation.source} / {annotation.confidence.toFixed(2)} / assigned{" "}
                  {annotation.assignedTo ?? "none"}
                </div>
              </div>
              <StatusPill status={annotation.reviewStatus} />
              <div className="segment-actions">
                <button
                  className="icon-button compact"
                  disabled={annotation.assignedTo === reviewerUserId}
                  onClick={() => onAssignAnnotation(annotation.id, reviewerUserId)}
                  title={`Assign to ${reviewerUserId}`}
                  type="button"
                >
                  <UserCheck size={14} />
                </button>
                <button
                  className="icon-button compact"
                  disabled={annotation.assignedTo === null}
                  onClick={() => onAssignAnnotation(annotation.id, null)}
                  title="Clear assignment"
                  type="button"
                >
                  <UserX size={14} />
                </button>
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

      <section className="panel-section">
        <div className="section-title">Episode label history</div>
        <div className="history-list">
          {recentLabelHistory.length === 0 ? (
            <div className="empty-state compact-empty-state">No label edits yet.</div>
          ) : (
            recentLabelHistory.map((event) => (
              <div className="history-row" key={event.eventId}>
                <div className="history-row-top">
                  <span className={`history-action history-action-${event.action}`}>
                    {event.action}
                  </span>
                  <span className="muted">{formatHistoryTime(event.createdAt)}</span>
                </div>
                <div className="history-label">{episodeLabelHistorySummary(event)}</div>
                <div className="muted mono">
                  {event.actor} / episode {event.episodeIndex}
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}

function episodeLabelHistorySummary(event: EpisodeLabelHistoryRecord): string {
  const after = event.after;
  if (after && Object.keys(after).length > 0) {
    return Object.entries(after)
      .map(([key, value]) => `${key}=${formatLabelValue(value)}`)
      .join(", ");
  }
  return `episode ${event.episodeIndex}`;
}

function formatLabelValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value.length > 40 ? `${value.slice(0, 37)}…` : value;
  }
  return String(value);
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

type RationaleRow = {
  id: string;
  label: string;
  confidence: number | null;
  rationale: string | null;
};

type SubtaskSummaryRow = {
  id: string;
  kind: string;
  label: string;
  startFrame: number;
  endFrame: number;
  percent: number;
  leftPercent: number;
  widthPercent: number;
  reviewStatus: ReviewStatus;
};

type SubtaskSummary = {
  coveragePercent: number;
  gapCount: number;
  overlapCount: number;
  rows: SubtaskSummaryRow[];
};

function episodeDraftFromProposal(
  current: EpisodeLabelDraft,
  annotation: SegmentAnnotation,
): EpisodeLabelDraft | null {
  const value = annotation.labelValue.trim();
  if (!value) {
    return null;
  }
  if (annotation.labelType === "episode_caption") {
    return { ...current, caption: value };
  }
  if (annotation.labelType === "failure_reason") {
    return { ...current, failureReason: value, successLabel: false };
  }
  if (annotation.labelType === "success_label") {
    const normalized = value.toLowerCase();
    if (["success", "succeeded", "true", "pass", "passed"].includes(normalized)) {
      return { ...current, successLabel: true, failureReason: "" };
    }
    if (["failure", "failed", "false", "fail"].includes(normalized)) {
      return { ...current, successLabel: false };
    }
    if (["unknown", "uncertain", "none", "null"].includes(normalized)) {
      return { ...current, successLabel: null };
    }
  }
  return null;
}

function computeSubtaskSummary(
  annotations: SegmentAnnotation[],
  frameCount: number,
): SubtaskSummary {
  const safeFrameCount = Math.max(1, frameCount);
  const maxFrame = safeFrameCount - 1;
  const rows = annotations
    .filter(
      (annotation) =>
        annotation.reviewStatus !== "rejected" &&
        ["phase", "subtask"].includes(annotation.labelType)
    )
    .sort((left, right) => left.startFrame - right.startFrame)
    .map((annotation) => {
      const startFrame = clampFrame(annotation.startFrame, maxFrame);
      const endFrame = Math.max(startFrame, clampFrame(annotation.endFrame, maxFrame));
      const length = endFrame - startFrame + 1;
      return {
        id: annotation.id,
        kind: annotation.labelType,
        label: annotation.labelValue,
        startFrame,
        endFrame,
        percent: (length / safeFrameCount) * 100,
        leftPercent: maxFrame > 0 ? (startFrame / maxFrame) * 100 : 0,
        widthPercent: Math.max(0.35, (length / safeFrameCount) * 100),
        reviewStatus: annotation.reviewStatus
      };
    });

  let overlapCount = 0;
  const merged: { startFrame: number; endFrame: number }[] = [];
  for (const row of rows) {
    const previous = merged[merged.length - 1];
    if (!previous || row.startFrame > previous.endFrame + 1) {
      merged.push({ startFrame: row.startFrame, endFrame: row.endFrame });
      continue;
    }
    if (row.startFrame <= previous.endFrame) {
      overlapCount += 1;
    }
    previous.endFrame = Math.max(previous.endFrame, row.endFrame);
  }

  const coveredFrames = merged.reduce(
    (total, range) => total + range.endFrame - range.startFrame + 1,
    0,
  );
  const gapCount = Math.max(0, merged.length - 1);
  return {
    coveragePercent: (coveredFrames / safeFrameCount) * 100,
    gapCount,
    overlapCount,
    rows
  };
}

function clampFrame(value: number, maxFrame: number): number {
  return Math.max(0, Math.min(maxFrame, Math.round(value)));
}

function responseRationaleRows(response: VlmResponseRecord): RationaleRow[] {
  const raw = response.rawResponse;
  const rationales = objectField(raw, "parsed_rationales");
  if (!rationales) {
    return [];
  }
  const rows: RationaleRow[] = [];
  for (const [key, value] of Object.entries(rationales)) {
    if (Array.isArray(value)) {
      value.forEach((item, index) => {
        const metadata = objectValue(item);
        if (metadata) {
          rows.push(rationaleRow(response, `${key}.${index}`, key, metadata));
        }
      });
      continue;
    }
    const metadata = objectValue(value);
    if (metadata) {
      rows.push(rationaleRow(response, key, key, metadata));
    }
  }
  return rows;
}

function rationaleRow(
  response: VlmResponseRecord,
  idSuffix: string,
  fallbackLabel: string,
  metadata: Record<string, unknown>,
): RationaleRow {
  const label = stringField(metadata, "label") ?? fallbackLabel;
  return {
    id: `${response.responseId}-${idSuffix}`,
    label,
    confidence: numberField(metadata, "confidence"),
    rationale: stringField(metadata, "rationale")
  };
}

function objectField(payload: Record<string, unknown>, key: string): Record<string, unknown> | null {
  return objectValue(payload[key]);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
