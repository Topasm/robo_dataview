import { Check, Pencil, Split, Trash2, X } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { Episode, SegmentAnnotation } from "@/lib/types";

type AnnotationEditorProps = {
  episode: Episode;
  annotations: SegmentAnnotation[];
};

export function AnnotationEditor({ episode, annotations }: AnnotationEditorProps) {
  return (
    <aside className="right-panel">
      <section className="panel-section">
        <div className="section-title">Episode Labels</div>
        <div className="form-grid">
          <label>
            Caption
            <textarea defaultValue={episode.caption} rows={3} />
          </label>
          <label>
            Quality
            <input defaultValue={episode.qualityScore.toFixed(2)} type="number" />
          </label>
          <label>
            Split
            <select defaultValue={episode.split}>
              <option>train</option>
              <option>val</option>
              <option>test</option>
            </select>
          </label>
        </div>
        <div className="segmented-control">
          <button className={episode.successLabel ? "active" : ""} type="button">
            <Check size={14} />
            Success
          </button>
          <button className={!episode.successLabel ? "active" : ""} type="button">
            <X size={14} />
            Failure
          </button>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">Segments</div>
        <div className="segment-list">
          {annotations.map((annotation) => (
            <div className="segment-row" key={annotation.id}>
              <div>
                <div className="segment-label">{annotation.labelValue}</div>
                <div className="muted mono">
                  {annotation.startFrame}-{annotation.endFrame} / {annotation.source} /{" "}
                  {annotation.confidence.toFixed(2)}
                </div>
              </div>
              <StatusPill status={annotation.reviewStatus} />
              <div className="segment-actions">
                <button className="icon-button compact" title="Edit segment" type="button">
                  <Pencil size={14} />
                </button>
                <button className="icon-button compact" title="Split segment" type="button">
                  <Split size={14} />
                </button>
                <button className="icon-button compact danger" title="Delete segment" type="button">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
