import { Box, ExternalLink } from "lucide-react";

type RerunPanelProps = {
  viewerUrl?: string | null;
};

export function RerunPanel({ viewerUrl }: RerunPanelProps) {
  return (
    <section className="rerun-panel">
      <div className="section-title">
        <Box size={16} />
        <span>Rerun</span>
      </div>
      <button className="text-button" disabled={!viewerUrl} type="button">
        <ExternalLink size={15} />
        Open cached recording
      </button>
      {viewerUrl ? (
        <iframe
          className="rerun-frame"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin"
          src={viewerUrl}
          title="Rerun Web Viewer"
        />
      ) : (
        <div className="rerun-canvas">
          <div className="axis x-axis" />
          <div className="axis y-axis" />
          <div className="axis z-axis" />
        </div>
      )}
    </section>
  );
}
