import { Download, PackageCheck } from "lucide-react";

export function ExportStrip() {
  return (
    <section className="export-strip">
      <div>
        <div className="section-title">
          <PackageCheck size={16} />
          <span>Export</span>
        </div>
        <div className="muted">3 selected / LeRobot target / accepted labels only</div>
      </div>
      <button className="text-button" type="button">
        <Download size={15} />
        Queue export
      </button>
    </section>
  );
}
