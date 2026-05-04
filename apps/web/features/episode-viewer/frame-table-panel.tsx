import { AlertTriangle, Hash, Tag } from "lucide-react";

import type { FrameRecord } from "@/lib/types";

type FrameTablePanelProps = {
  frames: FrameRecord[];
  onSelectFrame: (frameIndex: number) => void;
  selectedFrame: number;
  status: "idle" | "loading" | "ready" | "error";
};

export function FrameTablePanel({
  frames,
  onSelectFrame,
  selectedFrame,
  status
}: FrameTablePanelProps) {
  return (
    <section className="panel-section frame-table-panel">
      <div className="section-title">Frame Browser</div>
      <div className="frame-table-head">
        <span>Frame</span>
        <span>Time</span>
        <span>State</span>
        <span>Action</span>
        <span>Flags</span>
      </div>
      {frames.length > 0 ? (
        <div className="frame-table-body">
          {frames.map((frame) => (
            <button
              className={`frame-table-row${frame.frameIndex === selectedFrame ? " active" : ""}`}
              key={frame.frameIndex}
              onClick={() => onSelectFrame(frame.frameIndex)}
              type="button"
            >
              <span className="mono frame-table-index">
                <Hash size={11} />
                {frame.frameIndex}
              </span>
              <span className="mono">{formatMaybeNumber(frame.timestamp, 2)}</span>
              <span className="mono">{formatMaybeNumber(frame.stateNorm, 2)}</span>
              <span className="mono">{formatMaybeNumber(frame.actionNorm, 2)}</span>
              <FrameFlags frame={frame} />
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-state compact-empty-state">{statusText(status)}</div>
      )}
    </section>
  );
}

function FrameFlags({ frame }: { frame: FrameRecord }) {
  const activeLabelCount = frame.labels.filter((label) => label.reviewStatus !== "rejected").length;
  if (!frame.isBadFrame && activeLabelCount === 0) {
    return <span className="muted">none</span>;
  }
  return (
    <span className="frame-table-flags">
      {frame.isBadFrame ? (
        <span className="frame-table-bad-flag" title="Bad frame">
          <AlertTriangle size={12} />
        </span>
      ) : null}
      {activeLabelCount > 0 ? (
        <span className="frame-table-label-flag" title="Frame labels">
          <Tag size={12} />
          {activeLabelCount}
        </span>
      ) : null}
    </span>
  );
}

function formatMaybeNumber(value: number | null, digits: number): string {
  if (value === null || !Number.isFinite(value)) {
    return "none";
  }
  return value.toFixed(digits);
}

function statusText(status: FrameTablePanelProps["status"]): string {
  if (status === "loading") {
    return "Loading frames";
  }
  if (status === "error") {
    return "Frame rows unavailable";
  }
  return "No frame rows";
}
