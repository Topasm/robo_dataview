import { useState } from "react";
import { AlertTriangle, CheckCircle2, Hash, Tag } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { FrameRecord } from "@/lib/types";

type FrameMetadataPanelProps = {
  frame: FrameRecord | null;
  onSetBadFrame: (isBadFrame: boolean) => Promise<void>;
  onSetFrameLabel: (labelType: string, labelValue: string, enabled: boolean) => Promise<void>;
  selectedFrame: number;
  status: "idle" | "loading" | "ready" | "error";
};

const QUICK_FRAME_LABELS = [
  { label: "Important", type: "important_frame", value: "important_frame" },
  { label: "Occlusion", type: "occlusion", value: "occlusion" },
  { label: "Contact", type: "gripper_contact", value: "gripper_contact" }
];

export function FrameMetadataPanel({
  frame,
  onSetBadFrame,
  onSetFrameLabel,
  selectedFrame,
  status
}: FrameMetadataPanelProps) {
  const [isSaving, setIsSaving] = useState(false);
  const hasFrame = status === "ready" && frame !== null;
  const hasExactBadFrameLabel =
    frame?.labels.some(
      (label) => label.labelType === "bad_frame" && label.reviewStatus !== "rejected"
    ) ?? false;
  const canToggleBadFrame = hasFrame && (!frame.isBadFrame || hasExactBadFrameLabel);

  async function handleSetBadFrame(isBadFrame: boolean) {
    setIsSaving(true);
    try {
      await onSetBadFrame(isBadFrame);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSetFrameLabel(labelType: string, labelValue: string, enabled: boolean) {
    setIsSaving(true);
    try {
      await onSetFrameLabel(labelType, labelValue, enabled);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="panel-section frame-metadata-panel">
      <div className="section-title">Selected Frame</div>
      <div className="frame-status-row">
        <span className="frame-index-chip">
          <Hash size={13} />
          {hasFrame ? frame.frameIndex : selectedFrame}
        </span>
        {hasFrame && frame.isBadFrame ? (
          <span className="frame-bad-chip">
            <AlertTriangle size={13} />
            bad
          </span>
        ) : hasFrame ? (
          <span className="frame-ok-chip">
            <CheckCircle2 size={13} />
            ok
          </span>
        ) : (
          <span className="muted">{statusText(status)}</span>
        )}
      </div>

      {hasFrame ? (
        <>
          <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
            <button
              className={`text-button frame-mutation-button${frame.isBadFrame ? "" : " secondary-text-button"}`}
              disabled={isSaving || !canToggleBadFrame}
              onClick={() => void handleSetBadFrame(true)}
              type="button"
              style={{ flex: 1 }}
            >
              <AlertTriangle size={14} />
              Mark bad
            </button>
            <button
              className={`text-button frame-mutation-button${!frame.isBadFrame ? "" : " secondary-text-button"}`}
              disabled={isSaving || !canToggleBadFrame}
              onClick={() => void handleSetBadFrame(false)}
              type="button"
              style={{ flex: 1 }}
            >
              <CheckCircle2 size={14} />
              Approve
            </button>
          </div>
          <div className="frame-meta-grid">
            <MetaCell label="Timestamp" value={formatMaybeNumber(frame.timestamp, 4)} />
            <MetaCell label="Task" value={frame.taskIndex === null ? "none" : String(frame.taskIndex)} />
            <MetaCell label="State norm" value={formatMaybeNumber(frame.stateNorm, 3)} />
            <MetaCell label="Action norm" value={formatMaybeNumber(frame.actionNorm, 3)} />
          </div>
          <div className="frame-quick-labels">
            {QUICK_FRAME_LABELS.map((item) => {
              const isActive = hasActiveLabel(frame, item.type);
              return (
                <button
                  className={`quick-label-button${isActive ? " active" : ""}`}
                  disabled={isSaving}
                  key={item.type}
                  onClick={() => void handleSetFrameLabel(item.type, item.value, !isActive)}
                  type="button"
                >
                  {item.label}
                </button>
              );
            })}
          </div>
          <VectorPreview label="State" values={frame.observationState} />
          <VectorPreview label="Action" values={frame.action} />
          <div className="frame-labels">
            <div className="frame-subtitle">
              <Tag size={13} />
              Labels
            </div>
            {frame.labels.length === 0 ? (
              <div className="empty-state compact-empty-state">No labels</div>
            ) : (
              frame.labels.map((label) => (
                <div className="frame-label-row" key={label.annotationId}>
                  <div>
                    <div className="frame-label-title">{label.labelValue}</div>
                    <div className="muted mono">
                      {label.labelType} / {label.source} / {label.confidence.toFixed(2)}
                    </div>
                  </div>
                  <StatusPill status={label.reviewStatus} />
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        <div className="empty-state compact-empty-state">{statusText(status)}</div>
      )}
    </section>
  );
}

function hasActiveLabel(frame: FrameRecord, labelType: string): boolean {
  return frame.labels.some(
    (label) => label.labelType === labelType && label.reviewStatus !== "rejected"
  );
}

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="frame-meta-cell">
      <span>{label}</span>
      <strong className="mono">{value}</strong>
    </div>
  );
}

function VectorPreview({ label, values }: { label: string; values: number[] | null }) {
  if (!values || values.length === 0) {
    return (
      <div className="vector-preview">
        <div className="frame-subtitle">{label}</div>
        <div className="muted">none</div>
      </div>
    );
  }
  const preview = values.slice(0, 8).map((value) => formatMaybeNumber(value, 3));
  const maxAbsValue = values.length > 0 ? Math.max(...values.map(Math.abs)) : 0;
  const maxBarHeight = 20;

  return (
    <div className="vector-preview">
      <div className="frame-subtitle">
        <span>{label}</span>
        <span className="muted">{values.length} dim</span>
      </div>
      <div className="sparkline-container">
        {values.map((value, index) => {
          const height = maxAbsValue > 0 ? (Math.abs(value) / maxAbsValue) * maxBarHeight : 0;
          return (
            <div
              key={`spark-${index}`}
              className={`sparkline-bar${value < 0 ? " negative" : ""}`}
              style={{ height: `${Math.max(1, height)}px` }}
              title={`Dim ${index}: ${value.toFixed(4)}`}
            />
          );
        })}
      </div>
      <div className="vector-values mono">
        {preview.map((value, index) => (
          <span key={`${label}-${index}`}>{value}</span>
        ))}
        {values.length > preview.length ? <span>...</span> : null}
      </div>
    </div>
  );
}

function formatMaybeNumber(value: number | null, digits: number): string {
  if (value === null || !Number.isFinite(value)) {
    return "none";
  }
  return value.toFixed(digits);
}

function statusText(status: FrameMetadataPanelProps["status"]): string {
  if (status === "loading") {
    return "Loading frame";
  }
  if (status === "error") {
    return "Frame unavailable";
  }
  return "No frame selected";
}
