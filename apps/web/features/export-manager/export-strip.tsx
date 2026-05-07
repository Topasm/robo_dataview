import { AlertTriangle, Download, PackageCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { countOverlappingPairs } from "@/lib/clip-validation";
import type {
  ExportFormat,
  ExportRecord,
  JobRecord,
  SegmentAnnotation,
  SkillExportOptions
} from "@/lib/types";

type ExportStripProps = {
  annotations: SegmentAnnotation[];
  episodeIndex: number;
  exportJob: JobRecord | null;
  exportRecord: ExportRecord | null;
  onCreateExport: (
    format?: ExportFormat,
    scope?: "episode" | "split",
    options?: SkillExportOptions,
  ) => Promise<void>;
  split: string | null;
};

export function ExportStrip({
  annotations,
  episodeIndex,
  exportJob,
  exportRecord,
  onCreateExport,
  split
}: ExportStripProps) {
  const overlapCount = useMemo(() => countOverlappingPairs(annotations), [annotations]);
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
          Export accepted skill clips from episode #{episodeIndex} as train_skill_clips.lance
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
                skill segments {lanceArtifact.materialized.skill_segment_rows ?? 0} / train clips{" "}
                {lanceArtifact.materialized.train_skill_clip_rows ?? 0} / annotations{" "}
                {lanceArtifact.materialized.annotation_current_rows ??
                  lanceArtifact.materialized.annotation_rows ??
                  0}
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
            Current Episode
          </button>
          <button
            className={scope === "split" ? "active" : ""}
            disabled={!split || exportJobActive}
            onClick={() => setScope("split")}
            type="button"
          >
            Selected Split {split ?? ""}
          </button>
        </div>
        <div className="section-actions" style={{ flexDirection: "column", gap: "8px", alignItems: "stretch" }}>
        {overlapCount > 0 ? (
          <div className="export-overlap-warning" role="status">
            <AlertTriangle size={13} />
            <span>
              {overlapCount} overlapping skill clip pair{overlapCount === 1 ? "" : "s"} — server validation will report.
            </span>
          </div>
        ) : null}
        <button
          className="text-button primary-export-button"
          disabled={exportJobActive}
          onClick={() =>
            void onCreateExport("lance", scope, {
              clipLabelType: "skill",
              acceptedClipsOnly: true,
              materializeSkillClips: true,
              jitterOffsets: [0],
              copiesPerClip: 1
            })
          }
          type="button"
        >
          <Download size={15} />
          Export Skill Clips
        </button>
        <details className="advanced-menu export-advanced-menu">
          <summary>Augmentation Options</summary>
          <div className="advanced-menu-content">
            <label className="muted" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              Prefix Jitter:
              <select disabled style={{ background: "transparent", border: "none", color: "inherit", outline: "none", appearance: "none" }}>
                <option>Off</option>
              </select>
            </label>
            <label className="muted" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              Copies per clip:
              <select disabled style={{ background: "transparent", border: "none", color: "inherit", outline: "none", appearance: "none" }}>
                <option>1</option>
              </select>
            </label>
          </div>
        </details>
        <details className="advanced-menu export-advanced-menu">
          <summary>More formats</summary>
          <div className="advanced-menu-content">
            <button
              className="text-button secondary-text-button"
              disabled={exportJobActive}
              onClick={() => void onCreateExport("lerobot", scope)}
              type="button"
            >
              LeRobot
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={exportJobActive}
              onClick={() => void onCreateExport("jsonl", scope)}
              type="button"
            >
              JSONL
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={exportJobActive}
              onClick={() => void onCreateExport("vla", scope)}
              type="button"
            >
              VLA
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={exportJobActive}
              onClick={() => void onCreateExport("hf_dataset", scope)}
              type="button"
            >
              HF Dataset
            </button>
          </div>
        </details>
      </div>
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
