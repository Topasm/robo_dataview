import { useState } from "react";
import { Camera, Maximize2, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";

import { episodeVideoUrl } from "@/lib/api";
import type { Episode } from "@/lib/types";

type EpisodeViewerProps = {
  episode: Episode;
};

export function EpisodeViewer({ episode }: EpisodeViewerProps) {
  const [failedVideoKeys, setFailedVideoKeys] = useState<Set<string>>(new Set());

  function videoKey(camera: string) {
    return `${episode.datasetId}:${episode.episodeIndex}:${camera}`;
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

      <section className="camera-grid">
        {episode.cameraNames.map((camera) => (
          <div className="camera-pane" key={camera}>
            <div className="camera-pane-top">
              <span>{camera}</span>
              <Camera size={15} />
            </div>
            <div className="video-placeholder">
              {failedVideoKeys.has(videoKey(camera)) ? (
                <VideoBars />
              ) : (
                <video
                  className="video-element"
                  controls
                  muted
                  onError={() => markVideoFailed(camera)}
                  preload="metadata"
                  src={episodeVideoUrl(episode.datasetId, episode.episodeIndex, camera)}
                />
              )}
            </div>
          </div>
        ))}
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
          <div className="plot-title">State Norm</div>
          <div className="sparkline state-line" />
        </div>
        <div className="plot-panel">
          <div className="plot-title">Action Norm</div>
          <div className="sparkline action-line" />
        </div>
      </section>
    </main>
  );
}

function VideoBars() {
  return (
    <div className="video-bars">
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}
