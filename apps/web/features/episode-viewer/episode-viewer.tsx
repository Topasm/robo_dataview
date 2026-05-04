import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Camera, Loader2, Maximize2, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";

import { episodeVideoUrl, fetchStateActionSummary } from "@/lib/api";
import type { Episode, StateActionSummary } from "@/lib/types";

type EpisodeViewerProps = {
  episode: Episode;
};

export function EpisodeViewer({ episode }: EpisodeViewerProps) {
  const [activeCamera, setActiveCamera] = useState(episode.cameraNames[0] ?? "");
  const [failedVideoKeys, setFailedVideoKeys] = useState<Set<string>>(new Set());
  const [loadedVideoKeys, setLoadedVideoKeys] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState<StateActionSummary | null>(null);
  const [summaryStatus, setSummaryStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    setActiveCamera((current) => {
      if (current && episode.cameraNames.includes(current)) {
        return current;
      }
      return episode.cameraNames[0] ?? "";
    });
  }, [episode.cameraNames]);

  useEffect(() => {
    let isCurrent = true;
    setSummary(null);
    setSummaryStatus("loading");
    fetchStateActionSummary(episode.datasetId, episode.episodeIndex)
      .then((nextSummary) => {
        if (!isCurrent) {
          return;
        }
        setSummary(nextSummary);
        setSummaryStatus("ready");
      })
      .catch(() => {
        if (!isCurrent) {
          return;
        }
        setSummaryStatus("error");
      });
    return () => {
      isCurrent = false;
    };
  }, [episode.datasetId, episode.episodeIndex]);

  const activeVideoKey = activeCamera ? videoKey(activeCamera) : "";
  const activeVideoFailed = activeCamera ? failedVideoKeys.has(activeVideoKey) : false;
  const activeVideoLoaded = activeCamera ? loadedVideoKeys.has(activeVideoKey) : false;
  const summaryFallback = useMemo<StateActionSummary>(
    () => ({
      datasetId: episode.datasetId,
      episodeIndex: episode.episodeIndex,
      frameCount: episode.length,
      stateDim: null,
      actionDim: null,
      stateNormMin: null,
      stateNormMax: null,
      actionNormMin: null,
      actionNormMax: null
    }),
    [episode.datasetId, episode.episodeIndex, episode.length],
  );
  const displayedSummary = summary ?? summaryFallback;

  function videoKey(camera: string) {
    return `${episode.datasetId}:${episode.episodeIndex}:${camera}`;
  }

  function markVideoLoaded(camera: string) {
    setLoadedVideoKeys((current) => {
      const next = new Set(current);
      next.add(videoKey(camera));
      return next;
    });
  }

  function markVideoFailed(camera: string) {
    setFailedVideoKeys((current) => {
      const next = new Set(current);
      next.add(videoKey(camera));
      return next;
    });
  }

  return (
    <main className="main-viewer">
      <div className="viewer-toolbar">
        <div>
          <div className="viewer-title">Episode #{episode.episodeIndex}</div>
          <div className="muted">
            {episode.caption} / {episode.length} frames / {episode.fps} FPS
          </div>
        </div>
        <div className="toolbar-actions">
          <button className="icon-button" title="Reset view" type="button">
            <RotateCcw size={16} />
          </button>
          <button className="icon-button" title="Fullscreen" type="button">
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      <section className="camera-preview">
        <div className="active-camera-stage">
          <div className="camera-pane-top">
            <span className="camera-name" title={activeCamera || "No camera available"}>
              {activeCamera || "No camera available"}
            </span>
            <span className="camera-count">
              <Camera size={15} />
              {episode.cameraNames.length}
            </span>
          </div>
          <div className="video-placeholder">
            {!activeCamera ? (
              <VideoMessage icon={<Camera size={18} />} label="No camera streams in episode metadata" />
            ) : activeVideoFailed ? (
              <VideoMessage icon={<AlertTriangle size={18} />} label="Video stream failed to load" />
            ) : (
              <>
                {!activeVideoLoaded ? (
                  <VideoMessage icon={<Loader2 className="spin-icon" size={18} />} label="Loading video metadata" />
                ) : null}
                <video
                  key={activeVideoKey}
                  className="video-element"
                  controls
                  muted
                  onCanPlay={() => markVideoLoaded(activeCamera)}
                  onError={() => markVideoFailed(activeCamera)}
                  preload="metadata"
                  src={episodeVideoUrl(episode.datasetId, episode.episodeIndex, activeCamera)}
                />
              </>
            )}
          </div>
        </div>

        <div className="camera-selector" aria-label="Camera selection">
          {episode.cameraNames.map((camera) => {
            const key = videoKey(camera);
            const isActive = camera === activeCamera;
            const status = failedVideoKeys.has(key) ? "error" : loadedVideoKeys.has(key) ? "ready" : "idle";
            return (
              <button
                className={`camera-select-button${isActive ? " active" : ""}`}
                key={camera}
                onClick={() => setActiveCamera(camera)}
                title={camera}
                type="button"
              >
                <span className="camera-select-name">{camera}</span>
                <span className={`camera-select-status camera-status-${status}`}>
                  {status}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="playback-bar">
        <button className="icon-button" title="Previous segment" type="button">
          <SkipBack size={16} />
        </button>
        <button className="primary-icon-button" title="Play" type="button">
          <Play size={16} />
        </button>
        <button className="icon-button" title="Next segment" type="button">
          <SkipForward size={16} />
        </button>
        <div className="scrubber">
          <div className="scrubber-fill" />
          <div className="scrubber-thumb" />
        </div>
        <span className="mono">00:03.24</span>
      </section>

      <section className="state-action-panel">
        <div className="plot-panel">
          <div className="plot-title-row">
            <span className="plot-title">State Norm</span>
            <span className="plot-dim">{formatDim(displayedSummary.stateDim)}</span>
          </div>
          <NormRange
            max={displayedSummary.stateNormMax}
            min={displayedSummary.stateNormMin}
            status={summaryStatus}
          />
        </div>
        <div className="plot-panel">
          <div className="plot-title-row">
            <span className="plot-title">Action Norm</span>
            <span className="plot-dim">{formatDim(displayedSummary.actionDim)}</span>
          </div>
          <NormRange
            max={displayedSummary.actionNormMax}
            min={displayedSummary.actionNormMin}
            status={summaryStatus}
          />
        </div>
        <div className="state-action-meta">
          <span>{displayedSummary.frameCount.toLocaleString()} frames</span>
          <span>{summaryStatus === "error" ? "summary unavailable" : summaryStatus}</span>
        </div>
      </section>
    </main>
  );
}

function VideoMessage({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="video-message">
      {icon}
      <span>{label}</span>
    </div>
  );
}

function NormRange({
  max,
  min,
  status
}: {
  max: number | null;
  min: number | null;
  status: "loading" | "ready" | "error";
}) {
  if (status === "loading") {
    return <div className="norm-empty">Loading summary...</div>;
  }
  if (min === null || max === null) {
    return <div className="norm-empty">No numeric data</div>;
  }
  const fillWidth = Math.max(4, Math.min(100, Math.abs(max - min) * 100));
  return (
    <div className="norm-range">
      <div className="norm-track">
        <div className="norm-fill" style={{ width: `${fillWidth}%` }} />
      </div>
      <div className="norm-values">
        <span>min {formatNumber(min)}</span>
        <span>max {formatNumber(max)}</span>
      </div>
    </div>
  );
}

function formatDim(value: number | null) {
  return value === null ? "dim unknown" : `${value} dim`;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}
