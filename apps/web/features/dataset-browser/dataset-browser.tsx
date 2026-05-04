import { useState } from "react";
import { Database, FolderOpen, SlidersHorizontal } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { DatasetSummary } from "@/lib/types";

type DatasetBrowserProps = {
  summary: DatasetSummary;
  onOpenDataset: (uri: string) => Promise<void>;
};

export function DatasetBrowser({ summary, onOpenDataset }: DatasetBrowserProps) {
  const [uri, setUri] = useState("hf://datasets/lance-format/lerobot-xvla-soft-fold/data");
  const [isOpening, setIsOpening] = useState(false);
  const reviewedPercent =
    summary.episodeCount === 0 ? 0 : Math.round((summary.reviewedCount / summary.episodeCount) * 100);

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
