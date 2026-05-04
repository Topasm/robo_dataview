import { Box, ExternalLink } from "lucide-react";

export function RerunPanel() {
  return (
    <section className="rerun-panel">
      <div className="section-title">
        <Box size={16} />
        <span>Rerun</span>
      </div>
      <button className="text-button" type="button">
        <ExternalLink size={15} />
        Open cached recording
      </button>
      <div className="rerun-canvas">
        <div className="axis x-axis" />
        <div className="axis y-axis" />
        <div className="axis z-axis" />
      </div>
    </section>
  );
}
