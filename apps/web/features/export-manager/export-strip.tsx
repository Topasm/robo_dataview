import { Download, PackageCheck } from "lucide-react";

import type { ExportRecord } from "@/lib/types";

type ExportStripProps = {
  episodeIndex: number;
  exportRecord: ExportRecord | null;
  onCreateExport: () => Promise<void>;
};

export function ExportStrip({ episodeIndex, exportRecord, onCreateExport }: ExportStripProps) {
  const lerobotArtifact = exportRecord?.artifacts?.lerobot_v3;
  const validation = lerobotArtifact?.validation;

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
            {lerobotArtifact.materialized ? (
              <span>
                data rows {lerobotArtifact.materialized.frame_rows ?? 0} / videos{" "}
                {lerobotArtifact.materialized.video_files ?? 0}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      <button className="text-button" onClick={onCreateExport} type="button">
        <Download size={15} />
        Export selected
      </button>
    </section>
  );
}
