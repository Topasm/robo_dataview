import { Download, PackageCheck } from "lucide-react";
import { useState } from "react";

import type { ExportFormat, ExportRecord, JobRecord } from "@/lib/types";

type ExportStripProps = {
  episodeIndex: number;
  exportJob: JobRecord | null;
  exportRecord: ExportRecord | null;
  onCreateExport: (
    format?: ExportFormat,
    scope?: "episode" | "split",
  ) => Promise<void>;
  split: string | null;
};

export function ExportStrip({
  episodeIndex,
  exportJob,
  exportRecord,
  onCreateExport,
  split
}: ExportStripProps) {
  const [scope, setScope] = useState<"episode" | "split">("episode");
  const exportJobActive = exportJob ? !["succeeded", "failed"].includes(exportJob.status) : false;
  const exportProgressPercent = Math.round(Math.max(0, Math.min(1, exportJob?.progress ?? 0)) * 100);
  const lerobotArtifact = exportRecord?.artifacts?.lerobot_v3;
  const lanceArtifact = exportRecord?.artifacts?.lance_subset;
  const jsonlArtifact = exportRecord?.artifacts?.jsonl;
  const vlaArtifact = exportRecord?.artifacts?.vla_jsonl;
  const hfDatasetArtifact = exportRecord?.artifacts?.hf_dataset;
  const validation = lerobotArtifact?.validation;
  const lanceValidation = lanceArtifact?.validation;

  return (
    <section className="export-strip">
      <div>
        <div className="section-title">
          <PackageCheck size={16} />
          <span>Export</span>
        </div>
        <div className="muted">
          Episode #{episodeIndex} / LeRobot target / accepted labels only
        </div>
        {exportRecord ? (
          <div className="muted">
            {exportRecord.status}: {exportRecord.outputUri ?? exportRecord.message}
          </div>
        ) : null}
        {exportJob ? (
          <div className="muted">
            Job {exportJob.status} {exportProgressPercent}%:{" "}
            {exportJob.exportUri ?? exportJob.message ?? exportJob.createdExportId}
          </div>
        ) : null}
        {lerobotArtifact ? (
          <div className="export-artifact">
            <span>{lerobotArtifact.materialization_status ?? "metadata_only"}</span>
            <span>{lerobotArtifact.root}</span>
            {validation ? (
              <span>
                metadata {validation.metadata_ok ? "ok" : "check"} / episodes{" "}
                {validation.episode_count ?? 0} / frames {validation.frame_count ?? 0}
              </span>
            ) : null}
            {validation?.official_loader ? (
              <span>
                loader {loaderStatus(validation.official_loader)} / loadable{" "}
                {validation.lerobot_loadable ? "yes" : "no"}
                {validation.loadability_basis ? ` (${validation.loadability_basis})` : ""}
              </span>
            ) : null}
            {lerobotArtifact.materialized ? (
              <span>
                data rows {lerobotArtifact.materialized.frame_rows ?? 0} / videos{" "}
                {lerobotArtifact.materialized.video_files ?? 0}
              </span>
            ) : null}
          </div>
        ) : null}
        {lanceArtifact ? (
          <div className="export-artifact">
            <span>Lance subset</span>
            <span>{lanceArtifact.root}</span>
            {lanceValidation ? (
              <span>
                metadata {lanceValidation.metadata_ok ? "ok" : "check"} / episodes{" "}
                {lanceValidation.episode_count ?? 0} / frames {lanceValidation.frame_count ?? 0}
              </span>
            ) : null}
            {lanceArtifact.materialized ? (
              <span>
                annotations {lanceArtifact.materialized.annotation_rows ?? 0}
              </span>
            ) : null}
          </div>
        ) : null}
        {jsonlArtifact ? (
          <ExportArtifactSummary artifact={jsonlArtifact} label="JSONL" />
        ) : null}
        {vlaArtifact ? (
          <ExportArtifactSummary artifact={vlaArtifact} label="VLA JSONL" />
        ) : null}
        {hfDatasetArtifact ? (
          <ExportArtifactSummary artifact={hfDatasetArtifact} label="HF Dataset" />
        ) : null}
      </div>
      <div className="export-actions">
        <div className="segmented-control export-scope-control">
          <button
            className={scope === "episode" ? "active" : ""}
            disabled={exportJobActive}
            onClick={() => setScope("episode")}
            type="button"
          >
            Episode
          </button>
          <button
            className={scope === "split" ? "active" : ""}
            disabled={!split || exportJobActive}
            onClick={() => setScope("split")}
            type="button"
          >
            Split {split ?? ""}
          </button>
        </div>
        <button
          className="text-button"
          disabled={exportJobActive}
          onClick={() => void onCreateExport("lerobot", scope)}
          type="button"
        >
          <Download size={15} />
          LeRobot
        </button>
        <button
          className="text-button"
          disabled={exportJobActive}
          onClick={() => void onCreateExport("lance", scope)}
          type="button"
        >
          <Download size={15} />
          Lance
        </button>
        <button
          className="text-button"
          disabled={exportJobActive}
          onClick={() => void onCreateExport("jsonl", scope)}
          type="button"
        >
          <Download size={15} />
          JSONL
        </button>
        <button
          className="text-button"
          disabled={exportJobActive}
          onClick={() => void onCreateExport("vla", scope)}
          type="button"
        >
          <Download size={15} />
          VLA
        </button>
        <button
          className="text-button"
          disabled={exportJobActive}
          onClick={() => void onCreateExport("hf_dataset", scope)}
          type="button"
        >
          <Download size={15} />
          HF Dataset
        </button>
      </div>
    </section>
  );
}

function ExportArtifactSummary({
  artifact,
  label
}: {
  artifact: { root?: string; materialized?: Record<string, number | undefined> };
  label: string;
}) {
  const materialized = artifact.materialized ?? {};
  return (
    <div className="export-artifact">
      <span>{label}</span>
      <span>{artifact.root}</span>
      <span>
        {Object.entries(materialized)
          .map(([key, value]) => `${key} ${value ?? 0}`)
          .join(" / ")}
      </span>
    </div>
  );
}

function loaderStatus(loader: {
  available?: boolean;
  ok?: boolean | null;
}): string {
  if (!loader.available) {
    return "unavailable";
  }
  if (loader.ok) {
    return "ok";
  }
  return "check";
}
