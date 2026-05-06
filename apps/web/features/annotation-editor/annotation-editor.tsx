import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bot, Check, Plus, Save, Trash2, X } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { FrameMetadataPanel } from "@/features/episode-viewer/frame-metadata-panel";
import { HUMANOID_SKILLS, SKILL_LABEL_TYPE, skillByName } from "@/lib/skill-vocabulary";
import type {
  Episode,
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
  reviewStatus?: ReviewStatus;
  metadata?: SegmentAnnotation["metadata"];
};

type InspectorTab = "skills" | "frame";

type AnnotationEditorProps = {
  episode: Episode;
  annotationHistory: AnnotationHistoryRecord[];
  annotations: SegmentAnnotation[];
  clipStart: number | null;
  clipEnd: number | null;
  compact?: boolean;
  selectedFrame: number;
  selectedFrameRecord: FrameRecord | null;
  selectedFrameStatus: "idle" | "loading" | "ready" | "error";
  selectedClipId: string | null;
  selectedSkillId: number;
  reviewerUserId: string;
  vlmJob: JobRecord | null;
  vlmResponses: VlmResponseRecord[];
  onAssignAnnotation: (annotationId: string, assignedTo: string | null) => Promise<void>;
  onCreateSegment: (draft: AnnotationDraft) => Promise<void>;
  onDeleteSegment: (annotationId: string) => Promise<void>;
  onRunVlmLabel: () => Promise<void>;
  onSetClipStart: (frame: number | null) => void;
  onSetClipEnd: (frame: number | null) => void;
  onSelectClip: (annotationId: string | null) => void;
  onSetSelectedSkillId: (id: number) => void;
  onUpdateSelectedFrameLabel: (
    labelType: string,
    labelValue: string,
    labelEnabled: boolean,
  ) => Promise<void>;
  onUpdateSelectedFrameBadFlag: (isBadFrame: boolean) => Promise<void>;
  onUpdateSegment: (annotationId: string, draft: AnnotationDraft) => Promise<void>;
  onUpdateReviewStatus: (annotationId: string, status: ReviewStatus) => Promise<void>;
};

const QUICK_CLIP_QUALITY = [
  { label: "Keep", reviewStatus: "accepted" as ReviewStatus, quality: 1.0 },
  { label: "Usable", reviewStatus: "accepted" as ReviewStatus, quality: 0.7 },
  { label: "Bad", reviewStatus: "edited" as ReviewStatus, quality: 0.3 },
  { label: "Discard", reviewStatus: "rejected" as ReviewStatus, quality: 0.0 }
];

export function AnnotationEditor({
  episode,
  annotationHistory,
  annotations,
  clipStart,
  clipEnd,
  compact = false,
  selectedFrame,
  selectedFrameRecord,
  selectedFrameStatus,
  selectedClipId,
  selectedSkillId,
  // reviewerUserId not destructured — admin actions removed
  vlmJob,
  vlmResponses,
  // onAssignAnnotation available via props but not used in UI after admin actions removal
  onCreateSegment,
  onDeleteSegment,
  onRunVlmLabel,
  onSetClipStart,
  onSetClipEnd,
  onSelectClip,
  onSetSelectedSkillId,
  onUpdateSelectedFrameLabel,
  onUpdateSelectedFrameBadFlag,
  onUpdateSegment,
  onUpdateReviewStatus
}: AnnotationEditorProps) {
  const [draft, setDraft] = useState<AnnotationDraft>({
    labelType: "phase",
    labelValue: "phase_label",
    startFrame: 0,
    endFrame: Math.max(0, Math.min(episode.length - 1, 30))
  });
  const [editingRows, setEditingRows] = useState<Record<string, AnnotationDraft>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isBulkReviewing, setIsBulkReviewing] = useState(false);
  const [isRunningVlm, setIsRunningVlm] = useState(false);
  const [activeTab, setActiveTab] = useState<InspectorTab>("skills");
  const skillClips = annotations.filter((a) => a.labelType === SKILL_LABEL_TYPE);
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
  const rationaleRows = vlmResponses.flatMap(responseRationaleRows).slice(0, 6);
  const subtaskSummary = useMemo(
    () => computeSubtaskSummary(annotations, episode.length),
    [annotations, episode.length]
  );

  useEffect(() => {
    setDraft((current) => ({
      ...current,
      endFrame: Math.max(0, Math.min(episode.length - 1, current.endFrame))
    }));
  }, [episode]);

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


  async function handleApplyGeneratedProposal(annotation: SegmentAnnotation) {
    await onUpdateReviewStatus(annotation.id, "accepted");
  }

  return (
    <aside className="right-panel inspector-panel">
      <div className="inspector-tabs" role="tablist" aria-label="Inspector">
        <button
          className={activeTab === "skills" ? "active" : ""}
          onClick={() => setActiveTab("skills")}
          type="button"
        >
          Skill Clips ({skillClips.length})
        </button>
        <button
          className={activeTab === "frame" ? "active" : ""}
          onClick={() => setActiveTab("frame")}
          type="button"
        >
          Frame
        </button>
      </div>

      {activeTab === "skills" ? (
        <>
          <section className="panel-section">
            <div className="section-title">New Skill Clip</div>
            <div className="segment-form">
              <label>
                Skill
                <select
                  onChange={(event) => onSetSelectedSkillId(Number(event.target.value))}
                  value={selectedSkillId}
                >
                  {HUMANOID_SKILLS.map((skill) => (
                    <option key={skill.id} value={skill.id}>
                      {skill.id}: {skill.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Start
                <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                  <input
                    min={0}
                    onChange={(event) => onSetClipStart(event.target.value === "" ? null : Number(event.target.value))}
                    type="number"
                    value={clipStart ?? ""}
                    placeholder="press I"
                    style={{ flex: 1 }}
                  />
                  <button className="icon-button compact" onClick={() => onSetClipStart(selectedFrame)} title="Set to current frame (I)" type="button">I</button>
                </div>
              </label>
              <label>
                End
                <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                  <input
                    min={0}
                    onChange={(event) => onSetClipEnd(event.target.value === "" ? null : Number(event.target.value))}
                    type="number"
                    value={clipEnd ?? ""}
                    placeholder="press O"
                    style={{ flex: 1 }}
                  />
                  <button className="icon-button compact" onClick={() => onSetClipEnd(selectedFrame)} title="Set to current frame (O)" type="button">O</button>
                </div>
              </label>
              <button
                className="text-button segment-save-button"
                disabled={isSaving || clipStart === null || clipEnd === null}
                onClick={async () => {
                  const skill = HUMANOID_SKILLS[selectedSkillId];
                  if (!skill || clipStart === null || clipEnd === null) return;
                  setIsSaving(true);
                  try {
                    await onCreateSegment({
                      labelType: SKILL_LABEL_TYPE,
                      labelValue: skill.name,
                      startFrame: Math.min(clipStart, clipEnd),
                      endFrame: Math.max(clipStart, clipEnd),
                      metadata: { skillId: skill.id, qualityScore: null, successLabel: null }
                    });
                    onSetClipStart(null);
                    onSetClipEnd(null);
                  } finally {
                    setIsSaving(false);
                  }
                }}
                type="button"
              >
                <Plus size={15} />
                Add Clip
              </button>
            </div>
            <div className="shortcut-hints" style={{ marginTop: "8px" }}>
              <kbd>I</kbd> start <kbd>O</kbd> end <kbd>0-9</kbd> skill <kbd>A</kbd> add
            </div>
          </section>

          <section className="panel-section">
            <div className="section-title">Skill Clips</div>
            <div className="segment-list">
              {skillClips.length === 0 ? <div className="empty-state compact-empty-state">No skill clips. Use I/O to mark boundaries.</div> : null}
              {skillClips.map((clip) => {
                const skill = skillByName(clip.labelValue);
                return (
                  <div className={`segment-row${selectedClipId === clip.id ? " selected" : ""}`} key={clip.id}>
                    <div className="segment-edit-grid">
                      <button
                        className="segment-select-button"
                        onClick={() => onSelectClip(clip.id)}
                        style={{ color: skill?.color ?? "var(--text)" }}
                        type="button"
                      >
                        {skill?.label ?? clip.labelValue}
                      </button>
                      <span className="muted mono">f{clip.startFrame}–f{clip.endFrame}</span>
                      <StatusPill status={clip.reviewStatus} />
                    </div>
                    <div className="segment-actions">
                      <button className="icon-button compact" onClick={() => onUpdateReviewStatus(clip.id, "accepted")} title="Accept clip" type="button"><Check size={14} /></button>
                      <button className="icon-button compact" onClick={() => onUpdateReviewStatus(clip.id, "rejected")} title="Reject clip" type="button"><X size={14} /></button>
                      <button className="icon-button compact danger" onClick={() => onDeleteSegment(clip.id)} title="Delete clip" type="button"><Trash2 size={14} /></button>
                    </div>
                    <div className="clip-quality-actions">
                      {QUICK_CLIP_QUALITY.map((item) => (
                        <button
                          className={clip.metadata.qualityScore === item.quality ? "active" : ""}
                          key={item.label}
                          onClick={() =>
                            onUpdateSegment(clip.id, {
                              labelType: clip.labelType,
                              labelValue: clip.labelValue,
                              startFrame: clip.startFrame,
                              endFrame: clip.endFrame,
                              reviewStatus: item.reviewStatus,
                              metadata: { ...clip.metadata, qualityScore: item.quality }
                            })
                          }
                          type="button"
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel-section">
            <div className="section-title">Skill Coverage</div>
            <div className="metrics-grid">
              <div className="metric"><span>Clips</span><strong>{skillClips.length}</strong></div>
              <div className="metric"><span>Accepted</span><strong>{skillClips.filter((c) => c.reviewStatus === "accepted").length}</strong></div>
            </div>
          </section>
        </>
      ) : null}

      {activeTab === "frame" ? (
        <>
      <FrameMetadataPanel
        frame={selectedFrameRecord}
        onSetBadFrame={onUpdateSelectedFrameBadFlag}
        onSetFrameLabel={onUpdateSelectedFrameLabel}
        selectedFrame={selectedFrame}
        status={selectedFrameStatus}
      />

        </>
      ) : null}

      {!compact ? (
        <>
          <PanelDisclosure title="New Segment">
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
                  <option value="foot_slip">foot_slip</option>
                  <option value="fall_event">fall_event</option>
                  <option value="collision">collision</option>
                  <option value="foot_contact_issue">foot_contact_issue</option>
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
          </PanelDisclosure>

          <PanelDisclosure
            defaultOpen={annotations.length > 0}
            meta={annotations.length.toString()}
            title="Segments"
          >
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
                      <option value="foot_slip">foot_slip</option>
                      <option value="fall_event">fall_event</option>
                      <option value="collision">collision</option>
                      <option value="foot_contact_issue">foot_contact_issue</option>
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
                      onClick={() => onUpdateReviewStatus(annotation.id, "accepted")}
                      title="Keep segment"
                      type="button"
                    >
                      <Check size={14} />
                    </button>
                    <button
                      className="icon-button compact"
                      onClick={() => onUpdateReviewStatus(annotation.id, "rejected")}
                      title="Drop segment"
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

          </PanelDisclosure>

          <PanelDisclosure
            meta={`${subtaskSummary.coveragePercent.toFixed(0)}%`}
            title="Subtask Coverage"
          >
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
          </PanelDisclosure>
        </>
      ) : null}

      {!compact ? (
      <details className="panel-section sidebar-details">
        <summary>
          <span>Advanced Details</span>
        </summary>
        <div className="panel-disclosure-body">
          <PanelDisclosure
            meta={generatedProposals.length > 0 ? `${generatedProposals.length} pending` : "none"}
            title="AI Boundary Proposals"
          >
            <button
              className="text-button secondary-text-button vlm-run-button"
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
                <div className="vlm-progress">
                  <div className="progress-track compact-progress-track">
                    <div className="progress-fill" style={{ width: `${vlmProgressPercent}%` }} />
                  </div>
                  <span className="mono">{vlmProgressPercent}%</span>
                </div>
                <details className="advanced-menu compact-advanced-menu">
                  <summary>Job details</summary>
                  <div className="advanced-menu-content">
                    <span className="mono">
                      {vlmJob.promptTemplate}
                      {vlmJob.promptVersion ? `@${vlmJob.promptVersion}` : ""}
                    </span>
                    {vlmJob.provider ? <span className="mono">{vlmJob.provider}</span> : null}
                    {vlmJob.rawResponseIds.length > 0 ? (
                      <span className="mono">{vlmJob.rawResponseIds.length} raw</span>
                    ) : null}
                    {vlmJob.queueJobId ? <span className="mono">queue {vlmJob.queueJobId}</span> : null}
                  </div>
                </details>
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
                <div className="empty-state compact-empty-state">No pending boundary proposals.</div>
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
                        onClick={() => void handleApplyGeneratedProposal(annotation)}
                        title="Accept boundary proposal"
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
          </PanelDisclosure>

          <PanelDisclosure meta={recentHistory.length.toString()} title="History">
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
          </PanelDisclosure>

        </div>
      </details>
      ) : null}
    </aside>
  );
}

function PanelDisclosure({
  children,
  defaultOpen = false,
  meta,
  title
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  meta?: string;
  title: string;
}) {
  return (
    <details className="panel-section panel-disclosure" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {meta ? <span className="disclosure-meta">{meta}</span> : null}
      </summary>
      <div className="panel-disclosure-body">{children}</div>
    </details>
  );
}

function toDraft(annotation: SegmentAnnotation): AnnotationDraft {
  return {
    labelType: annotation.labelType,
    labelValue: annotation.labelValue,
    startFrame: annotation.startFrame,
    endFrame: annotation.endFrame,
    metadata: annotation.metadata
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
