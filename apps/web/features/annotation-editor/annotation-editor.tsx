import { useEffect, useState } from "react";
import { Check, Trash2, X } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { FrameMetadataPanel } from "@/features/episode-viewer/frame-metadata-panel";
import { HUMANOID_SKILLS, SKILL_LABEL_TYPE, skillByName } from "@/lib/skill-vocabulary";
import type { Episode, FrameRecord, ReviewStatus, SegmentAnnotation } from "@/lib/types";

type AnnotationDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
  reviewStatus?: ReviewStatus;
  metadata?: SegmentAnnotation["metadata"];
};

type InspectorTab = "skills" | "frame" | "coverage";

type AnnotationEditorProps = {
  episode: Episode;
  annotations: SegmentAnnotation[];
  clipStart: number | null;
  clipEnd: number | null;
  selectedFrame: number;
  selectedFrameRecord: FrameRecord | null;
  selectedFrameStatus: "idle" | "loading" | "ready" | "error";
  selectedClipId: string | null;
  selectedSkillId: number;
  onCreateSegment: (draft: AnnotationDraft) => Promise<void>;
  onDeleteSegment: (annotationId: string) => Promise<void>;
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
  annotations,
  clipStart,
  clipEnd,
  selectedFrame,
  selectedFrameRecord,
  selectedFrameStatus,
  selectedClipId,
  selectedSkillId,
  onCreateSegment,
  onDeleteSegment,
  onSetClipStart,
  onSetClipEnd,
  onSelectClip,
  onSetSelectedSkillId,
  onUpdateSelectedFrameLabel,
  onUpdateSelectedFrameBadFlag,
  onUpdateSegment,
  onUpdateReviewStatus
}: AnnotationEditorProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<InspectorTab>("skills");
  const skillClips = annotations.filter((a) => a.labelType === SKILL_LABEL_TYPE);

  // Clamping clipEnd against the episode length is handled by the parent's
  // I/O markers + 1-9 keymap. This effect just keeps stale state safe when
  // an episode swap shrinks the frame range.
  useEffect(() => {
    if (clipStart !== null && clipStart > episode.length - 1) {
      onSetClipStart(null);
    }
    if (clipEnd !== null && clipEnd > episode.length - 1) {
      onSetClipEnd(null);
    }
  }, [episode.length, clipStart, clipEnd, onSetClipStart, onSetClipEnd]);

  // onUpdateSelectedFrameLabel reserved for the Frame tab — referenced via prop
  // so future frame-label UIs can wire up without a signature change.
  void onUpdateSelectedFrameLabel;

  return (
    <aside className="right-panel inspector-panel">
      <div className="inspector-tabs" role="tablist" aria-label="Inspector">
        <button
          className={activeTab === "skills" ? "active" : ""}
          onClick={() => setActiveTab("skills")}
          type="button"
        >
          Clip ({skillClips.length})
        </button>
        <button
          className={activeTab === "frame" ? "active" : ""}
          onClick={() => setActiveTab("frame")}
          type="button"
        >
          Frame
        </button>
        <button
          className={activeTab === "coverage" ? "active" : ""}
          onClick={() => setActiveTab("coverage")}
          type="button"
        >
          Coverage
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
                      reviewStatus: "accepted",
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
                Add Clip
              </button>
            </div>
          </section>

          <section className="panel-section">
            <div className="section-title">Skill Clips</div>
            <div className="segment-list">
              {skillClips.length === 0 ? (
                <div className="empty-state compact-empty-state">
                  No skill clips. Use I/O to mark boundaries.
                </div>
              ) : null}
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
        </>
      ) : null}

      {activeTab === "frame" ? (
        <FrameMetadataPanel
          frame={selectedFrameRecord}
          onSetBadFrame={onUpdateSelectedFrameBadFlag}
          onSetFrameLabel={onUpdateSelectedFrameLabel}
          selectedFrame={selectedFrame}
          status={selectedFrameStatus}
        />
      ) : null}

      {activeTab === "coverage" ? (
        <section className="panel-section">
          <div className="section-title">Skill Coverage</div>
          <div className="metrics-grid">
            <div className="metric">
              <span>Clips</span>
              <strong>{skillClips.length}</strong>
            </div>
            <div className="metric">
              <span>Accepted</span>
              <strong>{skillClips.filter((c) => c.reviewStatus === "accepted").length}</strong>
            </div>
            <div className="metric">
              <span>Pending</span>
              <strong>{skillClips.filter((c) => c.reviewStatus === "pending").length}</strong>
            </div>
            <div className="metric">
              <span>Rejected</span>
              <strong>{skillClips.filter((c) => c.reviewStatus === "rejected").length}</strong>
            </div>
          </div>
        </section>
      ) : null}
    </aside>
  );
}
