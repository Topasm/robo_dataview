import { AlertTriangle, ChevronLeft, ChevronRight, ChevronsLeft, Hash, Tag } from "lucide-react";
import { useState } from "react";

import type { FrameRecord } from "@/lib/types";

type FrameTablePanelProps = {
  frameCount: number;
  frameLimit: number;
  frameStart: number;
  frames: FrameRecord[];
  onFrameLimitChange: (limit: number) => void;
  onFrameStartChange: (startFrame: number) => void;
  onSelectFrame: (frameIndex: number) => void;
  onSetBadFrame: (frameIndex: number, isBadFrame: boolean) => Promise<void>;
  returnedCount: number;
  selectedFrame: number;
  status: "idle" | "loading" | "ready" | "error";
};

export function FrameTablePanel({
  frameCount,
  frameLimit,
  frameStart,
  frames,
  onFrameLimitChange,
  onFrameStartChange,
  onSelectFrame,
  onSetBadFrame,
  returnedCount,
  selectedFrame,
  status
}: FrameTablePanelProps) {
  const [savingFrame, setSavingFrame] = useState<number | null>(null);
  const maxFrame = Math.max(0, frameCount - 1);
  const frameEnd = Math.min(maxFrame, frameStart + Math.max(1, frameLimit) - 1);
  const canGoBack = frameStart > 0;
  const canGoForward = frameEnd < maxFrame;

  async function handleToggleBadFrame(frame: FrameRecord) {
    setSavingFrame(frame.frameIndex);
    try {
      await onSetBadFrame(frame.frameIndex, !frame.isBadFrame);
    } finally {
      setSavingFrame(null);
    }
  }

  return (
    <section className="panel-section frame-table-panel">
      <div className="frame-table-toolbar">
        <div>
          <div className="section-title">Frame Browser</div>
          <div className="muted mono">
            f{frameStart}-{frameEnd} / {maxFrame} · {returnedCount} rows
          </div>
        </div>
        <div className="frame-table-controls">
          <button
            className="icon-button compact"
            disabled={!canGoBack}
            onClick={() => onFrameStartChange(0)}
            title="First page"
            type="button"
          >
            <ChevronsLeft size={13} />
          </button>
          <button
            className="icon-button compact"
            disabled={!canGoBack}
            onClick={() => onFrameStartChange(frameStart - frameLimit)}
            title="Previous page"
            type="button"
          >
            <ChevronLeft size={13} />
          </button>
          <select
            aria-label="Frame page size"
            onChange={(event) => onFrameLimitChange(Number(event.target.value))}
            value={frameLimit}
          >
            <option value={16}>16</option>
            <option value={32}>32</option>
            <option value={64}>64</option>
            <option value={128}>128</option>
          </select>
          <button
            className="icon-button compact"
            disabled={!canGoForward}
            onClick={() => onFrameStartChange(frameStart + frameLimit)}
            title="Next page"
            type="button"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      </div>
      <div className="frame-table-head">
        <span>Frame</span>
        <span>Time</span>
        <span>State</span>
        <span>Action</span>
        <span>Flags</span>
        <span>Edit</span>
      </div>
      {frames.length > 0 ? (
        <div className="frame-table-body">
          {frames.map((frame) => {
            const hasExactBadFrame = hasActiveLabel(frame, "bad_frame");
            const canToggleBadFrame = !frame.isBadFrame || hasExactBadFrame;
            return (
              <div
                className={`frame-table-row${frame.frameIndex === selectedFrame ? " active" : ""}`}
                key={frame.frameIndex}
                onClick={() => onSelectFrame(frame.frameIndex)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectFrame(frame.frameIndex);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <span className="mono frame-table-index">
                  <Hash size={11} />
                  {frame.frameIndex}
                </span>
                <span className="mono">{formatMaybeNumber(frame.timestamp, 2)}</span>
                <span className="mono">{formatMaybeNumber(frame.stateNorm, 2)}</span>
                <span className="mono">{formatMaybeNumber(frame.actionNorm, 2)}</span>
                <FrameFlags frame={frame} />
                <button
                  className={`frame-row-mutation${frame.isBadFrame ? " active" : ""}`}
                  disabled={savingFrame === frame.frameIndex || !canToggleBadFrame}
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleToggleBadFrame(frame);
                  }}
                  title={
                    canToggleBadFrame
                      ? frame.isBadFrame
                        ? "Clear bad frame label"
                        : "Mark bad frame"
                      : "Bad flag comes from a range or raw metadata"
                  }
                  type="button"
                >
                  {frame.isBadFrame ? "Clear" : "Bad"}
                </button>
              </div>
            );
          })}
        </div>
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
