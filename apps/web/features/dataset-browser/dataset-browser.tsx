import { useState } from "react";
import { Database, FolderOpen } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { DatasetHealth, DatasetSummary } from "@/lib/types";

type DatasetBrowserProps = {
  summaries: DatasetSummary[];
  selectedDatasetId: string;
  onOpenDataset: (uri: string) => Promise<void>;
  onSelectDataset: (datasetId: string) => Promise<void>;
};

export function DatasetBrowser({
  summaries,
  selectedDatasetId,
  onOpenDataset,
  onSelectDataset
}: DatasetBrowserProps) {
  const defaultDatasetUri =
    process.env.NEXT_PUBLIC_DEFAULT_DATASET_URI ??
    "hf://datasets/lance-format/lerobot-xvla-soft-fold/data";
  const [uri, setUri] = useState(defaultDatasetUri);
  const [isOpening, setIsOpening] = useState(false);

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

  const switchableSummaries = summaries.filter((item) => item.status !== "sample");
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [datasetOpenExpanded, setDatasetOpenExpanded] = useState(false);

  async function handleSelect(datasetId: string) {
    if (datasetId === selectedDatasetId || switchingId) {
      return;
    }
    setSwitchingId(datasetId);
    try {
      await onSelectDataset(datasetId);
    } finally {
      setSwitchingId(null);
    }
  }

  return (
    <section className="dataset-switcher panel-section">
      <div className="section-title">
        <Database size={16} />
        <span>Datasets</span>
        <span className="muted" style={{ marginLeft: "auto" }}>
          {switchableSummaries.length}
        </span>
      </div>
      {switchableSummaries.length === 0 ? (
        <div className="empty-state compact-empty-state">
          No datasets opened.
        </div>
      ) : (
        <div className="dataset-list">
          {switchableSummaries.map((item) => {
            const isActive = item.datasetId === selectedDatasetId;
            const isSwitching = switchingId === item.datasetId;
            const isClickable = item.status === "indexed";
            return (
              <button
                key={item.datasetId}
                className={`dataset-list-item${isActive ? " dataset-list-item--active" : ""}`}
                onClick={() => handleSelect(item.datasetId)}
                disabled={isSwitching || isActive || !isClickable}
                aria-pressed={isActive}
                title={isClickable ? undefined : `Cannot open: ${item.status}`}
                type="button"
              >
                <span className="dataset-list-name">{item.name}</span>
                <span className="dataset-list-meta">
                  <StatusPill status={item.status} />
                  <span className="muted mono">{item.episodeCount} ep</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
      <details
        className="dataset-open-details"
        open={switchableSummaries.length === 0 || datasetOpenExpanded}
        onToggle={(event) => setDatasetOpenExpanded(event.currentTarget.open)}
      >
        <summary>
          <FolderOpen size={14} />
          <span>Open dataset</span>
        </summary>
        <div className="dataset-open-form">
          <input
            aria-label="Open dataset by URI"
            placeholder="Path or hf:// URI…"
            onChange={(event) => setUri(event.target.value)}
            value={uri}
          />
          <button
            className="icon-button"
            disabled={isOpening || !uri.trim()}
            onClick={handleOpenDataset}
            title="Open dataset"
            type="button"
          >
            <FolderOpen size={16} />
          </button>
        </div>
      </details>
    </section>
  );
}

type DatasetMetaProps = {
  summary: DatasetSummary;
  health: DatasetHealth | null;
};

export function DatasetMeta({ summary, health }: DatasetMetaProps) {
  const checkedPercent =
    summary.episodeCount === 0 ? 0 : Math.round((summary.reviewedCount / summary.episodeCount) * 100);
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

  const isPublished = summary.storageLayout === "published_hf";
  const sourceCountSuffix =
    isPublished && summary.sourceSessionCount && summary.sourceSessionCount > 1
      ? ` · merged from ${summary.sourceSessionCount} sessions`
      : "";

  return (
    <section className="dataset-meta">
      {isPublished ? (
        <div
          className="muted"
          style={{
            fontSize: "11px",
            padding: "4px 8px",
            border: "1px solid var(--surface-3)",
            borderRadius: "var(--radius-pill, 999px)",
            display: "inline-block",
            marginBottom: "8px",
          }}
          title="Tables under data/ are treated as immutable; review and annotation edits are stored locally and never written back to this bundle."
        >
          HF dataset · annotations stored locally{sourceCountSuffix}
        </div>
      ) : null}
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
    </section>
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
