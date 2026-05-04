import { Download, PackageCheck } from "lucide-react";

import type { ExportRecord } from "@/lib/types";

type ExportStripProps = {
  episodeIndex: number;
  exportRecord: ExportRecord | null;
  onCreateExport: () => Promise<void>;
};

export function ExportStrip({ episodeIndex, exportRecord, onCreateExport }: ExportStripProps) {
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
      </div>
      <button className="text-button" onClick={onCreateExport} type="button">
        <Download size={15} />
        Export selected
      </button>
    </section>
  );
}
