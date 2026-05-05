import { useState } from "react";
import { Database, FolderOpen, SlidersHorizontal } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { DatasetSummary, SegmentAnnotation } from "@/lib/types";

type DatasetBrowserProps = {
  summary: DatasetSummary;
  reviewQueueRows: SegmentAnnotation[];
  reviewerUserId: string;
  onOpenDataset: (uri: string) => Promise<void>;
  onSelectEpisode: (episodeIndex: number) => void;
};

export function DatasetBrowser({
  summary,
  reviewQueueRows,
  reviewerUserId,
  onOpenDataset,
  onSelectEpisode
}: DatasetBrowserProps) {
  const defaultDatasetUri =
    process.env.NEXT_PUBLIC_DEFAULT_DATASET_URI ??
    "hf://datasets/lance-format/lerobot-xvla-soft-fold/data";
  const [uri, setUri] = useState(defaultDatasetUri);
  const [isOpening, setIsOpening] = useState(false);
  const reviewedPercent =
    summary.episodeCount === 0 ? 0 : Math.round((summary.reviewedCount / summary.episodeCount) * 100);
  const pendingRows = reviewQueueRows.filter((annotation) => annotation.reviewStatus === "pending");
  const assignedRows = pendingRows.filter((annotation) => annotation.assignedTo === reviewerUserId);
  const generatedRows = pendingRows.filter(
    (annotation) => annotation.source === "vlm" || annotation.source === "heuristic"
  );
  const queueRows = [
    ...assignedRows,
    ...pendingRows.filter((annotation) => annotation.assignedTo !== reviewerUserId)
  ].slice(0, 4);

  async function handleOpenDataset() {
    if (!uri.trim()) {
      return;
    }
    setIsOpening(true);
    try {
      await onOpenDataset(uri.trim());
    } finally {
      setIsOpening(false);
    }
  }

  return (
    <aside className="left-panel">
      <section className="panel-section">
        <div className="section-title">
          <Database size={16} />
          <span>Dataset</span>
        </div>
        <div className="dataset-name">{summary.name}</div>
        <div className="muted mono">{summary.uri}</div>
        <div className="dataset-status-row">
          <StatusPill status={summary.status} />
          {summary.message ? <span className="muted">{summary.message}</span> : null}
        </div>
        <div className="dataset-open-form">
          <input
            aria-label="Dataset URI"
            onChange={(event) => setUri(event.target.value)}
            value={uri}
          />
          <button
            className="icon-button"
            disabled={isOpening}
            onClick={handleOpenDataset}
            title="Open dataset"
            type="button"
          >
            <FolderOpen size={16} />
          </button>
        </div>
        <div className="section-actions">
          <button className="icon-button" title="Filter datasets" type="button">
            <SlidersHorizontal size={16} />
          </button>
        </div>
      </section>

      <section className="panel-section metrics-grid">
        <Metric label="Episodes" value={summary.episodeCount.toLocaleString()} />
        <Metric label="Frames" value={summary.frameCount.toLocaleString()} />
        <Metric label="FPS" value={summary.fps.toString()} />
        <Metric label="Cameras" value={summary.cameraNames.length.toString()} />
      </section>

      <section className="panel-section">
        <div className="section-title">Review</div>
        <div className="progress-row">
          <span>{summary.reviewedCount} reviewed</span>
          <span>{reviewedPercent}%</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${reviewedPercent}%` }} />
        </div>
        <div className="review-counts">
          <StatusPill status="accepted" />
          <span>{summary.acceptedCount}</span>
          <StatusPill status="rejected" />
          <span>{summary.rejectedCount}</span>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">Reviewer Queue</div>
        <div className="review-queue-metrics">
          <Metric label="Pending" value={pendingRows.length.toString()} />
          <Metric label="Mine" value={assignedRows.length.toString()} />
          <Metric label="Generated" value={generatedRows.length.toString()} />
        </div>
        <div className="review-queue-list">
          {queueRows.length === 0 ? (
            <div className="empty-state compact-empty-state">No pending annotations.</div>
          ) : (
            queueRows.map((annotation) => (
              <button
                className="review-queue-row"
                key={annotation.id}
                onClick={() => onSelectEpisode(annotation.episodeIndex)}
                type="button"
              >
                <span className="review-queue-label">{annotation.labelValue}</span>
                <span className="muted mono">
                  ep {annotation.episodeIndex} / f{annotation.startFrame}-{annotation.endFrame}
                </span>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">Cameras</div>
        <div className="camera-list">
          {summary.cameraNames.map((camera) => (
            <span className="camera-chip" key={camera}>
              {camera}
            </span>
          ))}
        </div>
      </section>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
