import type { SegmentAnnotation } from "@/lib/types";

type TimelinePanelProps = {
  annotations: SegmentAnnotation[];
  frameCount: number;
};

export function TimelinePanel({ annotations, frameCount }: TimelinePanelProps) {
  return (
    <section className="timeline-panel">
      <div className="timeline-ruler">
        <span>0</span>
        <span>{Math.round(frameCount * 0.25)}</span>
        <span>{Math.round(frameCount * 0.5)}</span>
        <span>{Math.round(frameCount * 0.75)}</span>
        <span>{frameCount}</span>
      </div>
      <div className="timeline-track">
        {annotations.map((annotation) => {
          const left = (annotation.startFrame / frameCount) * 100;
          const width = ((annotation.endFrame - annotation.startFrame + 1) / frameCount) * 100;
          return (
            <div
              className={`timeline-segment segment-${annotation.reviewStatus}`}
              key={annotation.id}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={annotation.labelValue}
            >
              {annotation.labelValue}
            </div>
          );
        })}
      </div>
    </section>
  );
}
