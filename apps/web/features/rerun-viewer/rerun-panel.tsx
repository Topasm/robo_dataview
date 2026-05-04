import dynamic from "next/dynamic";
import { Box, ExternalLink } from "lucide-react";

import type { JobRecord, RerunSession } from "@/lib/types";

const WebViewer = dynamic(() => import("@rerun-io/web-viewer-react"), {
  ssr: false,
  loading: () => <div className="rerun-viewer-loading">Loading Rerun viewer</div>
});

type RerunPanelProps = {
  job: JobRecord | null;
  session: RerunSession | null;
  viewerUrl?: string | null;
  onCreateSession: () => Promise<void>;
};

export function RerunPanel({ job, session, viewerUrl, onCreateSession }: RerunPanelProps) {
  const effectiveViewerUrl = session?.viewerUrl ?? viewerUrl;
  const jobActive = job ? !["succeeded", "failed"].includes(job.status) : false;
  const progressPercent = Math.round(Math.max(0, Math.min(1, job?.progress ?? 0)) * 100);

  return (
    <section className="rerun-panel">
      <div className="section-title">
        <Box size={16} />
        <span>Rerun</span>
      </div>
      <button className="text-button" disabled={jobActive} onClick={onCreateSession} type="button">
        <ExternalLink size={15} />
        Generate cached recording
      </button>
      {job ? (
        <div className="rerun-session-status">
          <span className={`status-pill status-${job.status}`}>{job.status}</span>
          <span className="muted">
            Job {progressPercent}%: {job.rerunRrdUrl ?? job.message ?? job.createdRerunSessionId}
          </span>
        </div>
      ) : null}
      {session ? (
        <div className="rerun-session-status">
          <span className={`status-pill status-${session.status}`}>{session.status}</span>
          {session.rrdUrl ? (
            <a href={session.rrdUrl} rel="noreferrer" target="_blank">
              .rrd
            </a>
          ) : null}
          {session.message ? <span className="muted">{session.message}</span> : null}
          <span className="muted">
            {session.cacheHit ? "cache hit" : "cache miss"} / cameras {session.cameraCount}
          </span>
          {session.cacheKey ? <span className="muted mono">{session.cacheKey}</span> : null}
        </div>
      ) : null}
      {session?.rrdUrl && session.status === "ready" ? (
        <div className="rerun-viewer-shell">
          <WebViewer height="100%" hide_welcome_screen rrd={session.rrdUrl} width="100%" />
        </div>
      ) : effectiveViewerUrl ? (
        <iframe
          className="rerun-frame"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin"
          src={effectiveViewerUrl}
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
