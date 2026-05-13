import { AlertTriangle, Download, PackageCheck, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { countOverlappingPairs } from "@/lib/clip-validation";
import type {
  ExportFormat,
  ExportHubUploadResult,
  ExportRecord,
  JobRecord,
  SegmentAnnotation,
  SkillExportOptions
} from "@/lib/types";
import { ExportHistory } from "./export-history";

type ExportStripProps = {
  annotations: SegmentAnnotation[];
  exportJob: JobRecord | null;
  exportRecord: ExportRecord | null;
  pastExports?: ExportRecord[];
  onCreateExport: (
    format?: ExportFormat,
    scope?: "dataset" | "episode" | "split",
    options?: SkillExportOptions,
  ) => Promise<void>;
  onUploadExportToHub: (exportId: string, repoId?: string) => Promise<ExportHubUploadResult>;
  split: string | null;
};

export function ExportStrip({
  annotations,
  exportJob,
  exportRecord,
  pastExports = [],
  onCreateExport,
  onUploadExportToHub,
  split
}: ExportStripProps) {
  const overlapCount = useMemo(() => countOverlappingPairs(annotations), [annotations]);
  const [scope, setScope] = useState<"dataset" | "episode" | "split">("dataset");
  const exportJobActive = exportJob ? !["succeeded", "failed"].includes(exportJob.status) : false;
  const exportProgressPercent = Math.round(Math.max(0, Math.min(1, exportJob?.progress ?? 0)) * 100);
  const lerobotArtifact = exportRecord?.artifacts?.lerobot_v3;
  const lanceArtifact = exportRecord?.artifacts?.lance_subset;
  const publishedLanceArtifact = exportRecord?.artifacts?.published_lance;
  const jsonlArtifact = exportRecord?.artifacts?.jsonl;
  const vlaArtifact = exportRecord?.artifacts?.vla_jsonl;
  const hfDatasetArtifact = exportRecord?.artifacts?.hf_dataset;
  const hubArtifact = exportRecord?.artifacts?.huggingface_hub;
  const validation = lerobotArtifact?.validation;
  const lanceValidation = lanceArtifact?.validation;
  const canUploadHub =
    exportRecord?.status === "succeeded" &&
    Boolean(publishedLanceArtifact?.root ?? lanceArtifact?.root);
  const [hubUpload, setHubUpload] = useState<ExportHubUploadResult | null>(null);
  const [hubUploadError, setHubUploadError] = useState<string | null>(null);
  const [hubUploading, setHubUploading] = useState(false);
  const [applySubmitting, setApplySubmitting] = useState(false);
  const applyLocalProgressPercent = useOperationProgress(applySubmitting);
  const hubUploadProgressPercent = useOperationProgress(hubUploading);
  const defaultHubRepoId = exportRecord?.hubRepoId ?? hubArtifact?.repo_id ?? "";
  const [hubRepoDraft, setHubRepoDraft] = useState(defaultHubRepoId);
  const applyBusy = applySubmitting || exportJobActive;
  const applyProgressPercent = exportJobActive ? exportProgressPercent : applyLocalProgressPercent;

  useEffect(() => {
    setHubUpload(null);
    setHubUploadError(null);
    setHubUploading(false);
    setHubRepoDraft(defaultHubRepoId);
  }, [defaultHubRepoId, exportRecord?.exportId]);

  async function handleHubUpload() {
    if (!exportRecord || hubUploading) {
      return;
    }
    setHubUploading(true);
    setHubUploadError(null);
    try {
      const result = await onUploadExportToHub(
        exportRecord.exportId,
        hubRepoDraft.trim() || undefined,
      );
      setHubUpload(result);
    } catch (error) {
      setHubUploadError(error instanceof Error ? error.message : String(error));
    } finally {
      setHubUploading(false);
    }
  }

  async function handleCreateExportClick(format: ExportFormat, options?: SkillExportOptions) {
    if (applyBusy) {
      return;
    }
    setApplySubmitting(true);
    try {
      await onCreateExport(format, scope, options);
    } finally {
      setApplySubmitting(false);
    }
  }

  return (
    <section className="export-strip">
      <div>
        <div className="section-title">
          <PackageCheck size={16} />
          <span>Apply to dataset</span>
        </div>
        <div className="muted">
          Applies the current curated dataset state under{" "}
          <code>data/exports/&lt;id&gt;/</code>. Upload replaces the HF repo cleanly and
          prunes older local export/annotation history. Exported Lance tables are
          renumbered from episode 0 after deletions.
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
        {applySubmitting || exportJobActive ? (
          <OperationProgress
            detail="metadata와 state/action stats를 다시 계산하는 중"
            label="Apply 진행 중"
            percent={applyProgressPercent}
          />
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
            {lanceArtifact.materialized || lanceValidation ? (
              <span>
                stats state{" "}
                {lanceArtifact.materialized?.state_stats_count ??
                  lanceValidation?.state_stats_count ??
                  0}{" "}
                / action{" "}
                {lanceArtifact.materialized?.action_stats_count ??
                  lanceValidation?.action_stats_count ??
                  0}
              </span>
            ) : null}
          </div>
        ) : null}
        {publishedLanceArtifact ? (
          <div className="export-artifact">
            <span>HF published layout</span>
            <span>{publishedLanceArtifact.root}</span>
            {publishedLanceArtifact.validation ? (
              <span>
                metadata {publishedLanceArtifact.validation.metadata_ok ? "ok" : "check"} /
                episodes {publishedLanceArtifact.validation.episode_count ?? 0} / frames{" "}
                {publishedLanceArtifact.validation.frame_count ?? 0}
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
        {canUploadHub ? (
          <div className="export-artifact export-hub-panel">
            <span>Hugging Face</span>
            <span>
              {hubUpload?.repoUrl ?? hubArtifact?.repo_url ?? "Upload this curated export?"}
            </span>
            <label className="export-hub-repo-row">
              <span>HF repo</span>
              <input
                aria-label="Hugging Face repository id"
                onChange={(event) => setHubRepoDraft(event.target.value)}
                placeholder="rllab-postech/data_pickup_tire"
                spellCheck={false}
                value={hubRepoDraft}
              />
            </label>
            <span className="export-hub-guide">
              한국어 안내: Apply는 전체 dataset 기준 curated export를 만들고, Upload는 위 HF
              repo를 깨끗한 새 commit으로 교체합니다. 업로드가 성공하면 이전 export와 annotation
              tombstone/history도 정리됩니다. 삭제된 episode를 제외한 export 데이터는 0번부터 다시
              번호가 매겨집니다.
            </span>
            {exportRecord?.hubRepoSource ? (
              <span className="export-hub-guide">
                기본값 출처: {hubRepoSourceLabel(exportRecord.hubRepoSource)}
              </span>
            ) : null}
            {hubUploading ? (
              <OperationProgress
                detail="파일 업로드와 HF commit 생성 중"
                label="HF upload 진행 중"
                percent={hubUploadProgressPercent}
              />
            ) : null}
            {hubUpload?.commitUrl ?? hubArtifact?.commit_url ? (
              <span>{hubUpload?.commitUrl ?? hubArtifact?.commit_url}</span>
            ) : hubUploadError ? (
              <span className="export-hub-error">{hubUploadError}</span>
            ) : null}
            <button
              className="text-button secondary-text-button"
              disabled={hubUploading || !hubRepoDraft.trim()}
              onClick={() => void handleHubUpload()}
              title="Upload this curated Lance export to Hugging Face"
              type="button"
            >
              <UploadCloud size={14} />
              {hubUploading
                ? "Uploading..."
                : hubArtifact || hubUpload
                  ? "Upload again"
                  : "Upload to HF"}
            </button>
          </div>
        ) : null}
      </div>
      <div className="export-actions">
        <div className="segmented-control export-scope-control">
          <button
            aria-label="Apply every episode in this dataset"
            aria-pressed={scope === "dataset"}
            className={scope === "dataset" ? "active" : ""}
            disabled={applyBusy}
            onClick={() => setScope("dataset")}
            title="Apply curation to the full dataset"
            type="button"
          >
            Full Dataset
          </button>
          <button
            className={scope === "episode" ? "active" : ""}
            disabled={applyBusy}
            onClick={() => setScope("episode")}
            title="Apply only the currently selected episode"
            aria-label="Apply only the current episode"
            aria-pressed={scope === "episode"}
            type="button"
          >
            Current Episode
          </button>
          <button
            className={scope === "split" ? "active" : ""}
            disabled={!split || applyBusy}
            onClick={() => setScope("split")}
            title="Apply every episode in the selected split (train/val/test)"
            aria-label="Apply every episode in the selected split"
            aria-pressed={scope === "split"}
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
          disabled={applyBusy}
          onClick={() =>
            void handleCreateExportClick("lance", {
              clipLabelType: "skill",
              acceptedClipsOnly: true,
              materializeSkillClips: true,
              jitterOffsets: [0],
              copiesPerClip: 1
            })
          }
          title="Apply the current curated dataset state under data/exports/."
          aria-label="Apply curated dataset state"
          type="button"
        >
          <Download size={15} />
          {applySubmitting ? "Applying..." : "Apply to dataset"}
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
          <summary title="Show alternative export formats (LeRobot v3, JSONL, VLA, HF Dataset)">More formats</summary>
          <div className="advanced-menu-content">
            <button
              className="text-button secondary-text-button"
              disabled={applyBusy}
              onClick={() => void handleCreateExportClick("lerobot")}
              title="Export as LeRobot v3 (manifest + Parquet + MP4 + SHA256 index)"
              type="button"
            >
              LeRobot
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={applyBusy}
              onClick={() => void handleCreateExportClick("jsonl")}
              title="Export as line-delimited JSON (one frame per line)"
              type="button"
            >
              JSONL
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={applyBusy}
              onClick={() => void handleCreateExportClick("vla")}
              title="Export as VLA training format (vision-language-action JSONL)"
              type="button"
            >
              VLA
            </button>
            <button
              className="text-button secondary-text-button"
              disabled={applyBusy}
              onClick={() => void handleCreateExportClick("hf_dataset")}
              title="Export as HuggingFace Datasets snapshot"
              type="button"
            >
              HF Dataset
            </button>
          </div>
        </details>
        <ExportHistory exports={pastExports} />
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

function OperationProgress({
  detail,
  label,
  percent
}: {
  detail: string;
  label: string;
  percent: number;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="export-progress" role="status">
      <div className="export-progress-header">
        <span>{label}</span>
        <span>{clamped}%</span>
      </div>
      <div
        aria-label={label}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={clamped}
        className="export-progress-track"
        role="progressbar"
      >
        <div className="export-progress-fill" style={{ width: `${clamped}%` }} />
      </div>
      <div className="export-progress-detail">{detail}</div>
    </div>
  );
}

function useOperationProgress(active: boolean): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!active) {
      setProgress(0);
      return undefined;
    }
    setProgress(8);
    const timer = window.setInterval(() => {
      setProgress((current) => {
        if (current >= 94) {
          return current;
        }
        return Math.min(94, current + Math.max(1, Math.round((94 - current) * 0.14)));
      });
    }, 450);
    return () => window.clearInterval(timer);
  }, [active]);

  return progress;
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

function hubRepoSourceLabel(source: string): string {
  if (source === "source_dataset") {
    return "원본 HF dataset";
  }
  if (source === "env:RLLAB_HF_REPO_ID") {
    return "API 환경변수 RLLAB_HF_REPO_ID";
  }
  if (source === "env:RLLAB_HF_NAMESPACE") {
    return "API 환경변수 RLLAB_HF_NAMESPACE";
  }
  return source;
}
