import { useState } from "react";
import { Database, FolderOpen } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { DatasetHealth, DatasetSummary, SegmentAnnotation } from "@/lib/types";

type DatasetBrowserProps = {
  summary: DatasetSummary;
  health: DatasetHealth | null;
  reviewQueueRows: SegmentAnnotation[];
  reviewerUserId: string;
  onOpenDataset: (uri: string) => Promise<void>;
  onSelectEpisode: (episodeIndex: number) => void;
};

export function DatasetBrowser({
  summary,
  health,
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
  const checkedPercent =
    summary.episodeCount === 0 ? 0 : Math.round((summary.reviewedCount / summary.episodeCount) * 100);
  const pendingRows = reviewQueueRows.filter((annotation) => annotation.reviewStatus === "pending");
  const badRows = reviewQueueRows.filter(
    (annotation) => annotation.labelType === "bad_range" || annotation.labelType === "bad_frame"
  );
  const autoRows = pendingRows.filter(
    (annotation) => annotation.source === "vlm" || annotation.source === "heuristic"
  );
  const queueRows = [
    ...pendingRows.filter((annotation) => annotation.assignedTo === reviewerUserId),
    ...pendingRows.filter((annotation) => annotation.assignedTo !== reviewerUserId)
  ].slice(0, 4);
  const coreTables =
    health?.tables.filter((table) => table.table === "episodes" || table.table === "frames") ?? [];
  const mediaTable = health?.tables.find((table) => table.table === "media") ?? null;
  const legacyVideosTable = health?.tables.find((table) => table.table === "videos") ?? null;
  const mediaValue = getMediaHealthValue(mediaTable, legacyVideosTable, health?.cameraCount ?? 0);
  const presentCoreTableCount = coreTables.filter((table) => table.present).length;
  const tableIssues =
    health?.tables.flatMap((table) => {
      if (table.table === "videos" && mediaTable?.present) {
        return [];
      }
      return [
        ...table.missingRequiredColumns.map((column) => `${table.table}: missing ${column}`),
        ...table.warnings.map((warning) => `${table.table}: ${warning}`)
      ];
    }) ?? [];
  const healthIssues = [...(health?.errors ?? []), ...(health?.warnings ?? []), ...tableIssues];
  const healthErrorCount = health?.errors.length ?? 0;
  const hasHealthErrors = healthErrorCount > 0;
  const hasHealthWarnings = healthIssues.length > 0;
  const healthStatus = hasHealthErrors ? "error" : hasHealthWarnings ? "warning" : "ready";
  const healthHeadline = hasHealthErrors
    ? `${healthErrorCount.toLocaleString()} error${healthErrorCount === 1 ? "" : "s"}`
    : hasHealthWarnings
      ? `${healthIssues.length.toLocaleString()} warning${healthIssues.length === 1 ? "" : "s"}`
      : "OK";

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
        <div className="dataset-status-row">
          <StatusPill status={summary.status} />
          {summary.message ? <span className="muted">{summary.message}</span> : null}
        </div>
      </section>

      <section className="panel-section review-queue-section">
        <div className="section-title">
          <span>Work Queue</span>
        </div>
        {pendingRows.length === 0 && badRows.length === 0 && autoRows.length === 0 ? (
          <div className="empty-state compact-empty-state">Queue clear.</div>
        ) : (
          <>
            <div className="review-queue-metrics">
              <Metric label="Need Check" value={pendingRows.length.toString()} />
              <Metric label="Bad" value={badRows.length.toString()} />
              <Metric label="Auto" value={autoRows.length.toString()} />
            </div>
            <div className="review-queue-list">
              {queueRows.map((annotation) => (
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
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel-section review-progress-section">
        <div className="section-title">
          <span>Dataset Progress</span>
          <span className="muted">{checkedPercent}%</span>
        </div>
        <div className="progress-row">
          <span>{summary.reviewedCount} checked</span>
          <span className="muted">{summary.episodeCount} total</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${checkedPercent}%` }} />
        </div>
        {summary.acceptedCount > 0 || summary.rejectedCount > 0 ? (
          <div className="review-counts">
            <StatusPill status="accepted" />
            <span>{summary.acceptedCount}</span>
            <StatusPill status="rejected" />
            <span>{summary.rejectedCount}</span>
          </div>
        ) : null}
      </section>

      <details className="panel-section sidebar-details">
        <summary>
          <span>Advanced Details</span>
        </summary>
        <div className="panel-disclosure-body">
          <div className="muted mono" style={{ marginBottom: "8px", wordBreak: "break-all" }}>{summary.uri}</div>
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
          
          <div className="metrics-grid" style={{ marginTop: "16px", marginBottom: "16px" }}>
            <Metric label="Episodes" value={summary.episodeCount.toLocaleString()} />
            <Metric label="Frames" value={summary.frameCount.toLocaleString()} />
            <Metric label="FPS" value={summary.fps.toString()} />
            <Metric label="Cameras" value={summary.cameraNames.length.toString()} />
          </div>

          {health ? (
            <div className="dataset-health" style={{ marginBottom: "16px" }}>
              <div className="health-status-row">
                <StatusPill status={healthStatus} />
                <span className="muted">{healthHeadline}</span>
              </div>
              <div className="health-details">
                <HealthFact label="Storage" value={health.storageModel} />
                <HealthFact label="Core" value={`${presentCoreTableCount}/${coreTables.length}`} />
                <HealthFact label="Media" value={mediaValue} />
              </div>
              {healthIssues.length > 0 ? (
                <div className="health-issues">
                  {healthIssues.slice(0, 3).map((issue) => (
                    <div className="health-issue" key={issue}>
                      {issue}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="camera-list">
            <div className="section-title" style={{ fontSize: "11px", marginBottom: "4px" }}>Cameras ({summary.cameraNames.length})</div>
            {summary.cameraNames.map((camera) => (
              <span className="camera-chip" key={camera}>
                {camera}
              </span>
            ))}
          </div>
        </div>
      </details>
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

function HealthFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="health-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function getMediaHealthValue(
  mediaTable: DatasetHealth["tables"][number] | null,
  legacyVideosTable: DatasetHealth["tables"][number] | null,
  cameraCount: number
) {
  if (mediaTable?.present) {
    const suffix = legacyVideosTable?.present ? " + legacy" : "";
    return `${formatRowCount(mediaTable.rowCount)}${suffix}`;
  }
  if (legacyVideosTable?.present) {
    return `legacy ${formatRowCount(legacyVideosTable.rowCount)}`;
  }
  if (cameraCount > 0) {
    return "episode";
  }
  return "none";
}

function formatRowCount(value: number | null) {
  if (value === null) {
    return "ready";
  }
  return `${value.toLocaleString()} row${value === 1 ? "" : "s"}`;
}
