"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import {
  AlertTriangle,
  Camera,
  Grid2x2,
  LayoutPanelLeft,
  Loader2,
  Maximize2,
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward
} from "lucide-react";

import { episodeVideoUrl, fetchEpisodeTimeseries } from "@/lib/api";
import type { Episode, EpisodeTimeseries } from "@/lib/types";

type EpisodeViewerProps = {
  episode: Episode;
};

type CameraLayout = "focus" | "grid";
type LoadStatus = "idle" | "ready" | "error";

const SYNC_DRIFT_SECONDS = 0.08;
const STEP_FRAMES = 1;
const JUMP_FRAMES = 30;

export function EpisodeViewer({ episode }: EpisodeViewerProps) {
  const cameraNames = episode.cameraNames;
  const fps = episode.fps > 0 ? episode.fps : 20;
  const frameCount = Math.max(1, episode.length || 0);
  const lastFrame = Math.max(0, frameCount - 1);

  const [layout, setLayout] = useState<CameraLayout>("focus");
  const [activeCamera, setActiveCamera] = useState<string>(cameraNames[0] ?? "");
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [videoStatus, setVideoStatus] = useState<Record<string, LoadStatus>>({});
  const [timeseries, setTimeseries] = useState<EpisodeTimeseries | null>(null);
  const [timeseriesStatus, setTimeseriesStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );

  const videoRefs = useRef<Map<string, HTMLVideoElement>>(new Map());
  const animationRef = useRef<number | null>(null);

  useEffect(() => {
    setActiveCamera((current) =>
      current && cameraNames.includes(current) ? current : cameraNames[0] ?? ""
    );
  }, [cameraNames]);

  useEffect(() => {
    setCurrentFrame(0);
    setIsPlaying(false);
    setVideoStatus({});
  }, [episode.datasetId, episode.episodeIndex]);

  useEffect(() => {
    let cancelled = false;
    setTimeseries(null);
    setTimeseriesStatus("loading");
    fetchEpisodeTimeseries(episode.datasetId, episode.episodeIndex)
      .then((next) => {
        if (cancelled) {
          return;
        }
        setTimeseries(next);
        setTimeseriesStatus("ready");
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setTimeseriesStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [episode.datasetId, episode.episodeIndex]);

  const seekVideosToFrame = useCallback(
    (frame: number) => {
      const target = frame / fps;
      videoRefs.current.forEach((video) => {
        if (Math.abs(video.currentTime - target) > SYNC_DRIFT_SECONDS) {
          video.currentTime = target;
        }
      });
    },
    [fps]
  );

  const setFrame = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(lastFrame, Math.round(next)));
      setCurrentFrame(clamped);
      seekVideosToFrame(clamped);
    },
    [lastFrame, seekVideosToFrame]
  );

  const handleTogglePlay = useCallback(() => {
    setIsPlaying((current) => !current);
  }, []);

  useEffect(() => {
    const videos = Array.from(videoRefs.current.values());
    if (videos.length === 0) {
      return;
    }
    if (isPlaying) {
      if (currentFrame >= lastFrame) {
        setFrame(0);
      }
      videos.forEach((video) => {
        const promise = video.play();
        if (promise && typeof promise.catch === "function") {
          promise.catch(() => undefined);
        }
      });
    } else {
      videos.forEach((video) => {
        video.pause();
      });
    }
    // We deliberately exclude currentFrame so toggling play does not stutter on tick updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying]);

  useEffect(() => {
    if (!isPlaying) {
      return;
    }
    let stopped = false;

    function step() {
      if (stopped) {
        return;
      }
      const refs = videoRefs.current;
      if (refs.size === 0) {
        animationRef.current = window.requestAnimationFrame(step);
        return;
      }
      const leader = refs.get(activeCamera) ?? refs.values().next().value ?? null;
      if (leader) {
        refs.forEach((video) => {
          if (
            video !== leader &&
            Math.abs(video.currentTime - leader.currentTime) > SYNC_DRIFT_SECONDS
          ) {
            video.currentTime = leader.currentTime;
          }
        });
        const frame = Math.min(lastFrame, Math.round(leader.currentTime * fps));
        setCurrentFrame((current) => (current === frame ? current : frame));
        if (frame >= lastFrame) {
          setIsPlaying(false);
          return;
        }
      }
      animationRef.current = window.requestAnimationFrame(step);
    }

    animationRef.current = window.requestAnimationFrame(step);
    return () => {
      stopped = true;
      if (animationRef.current !== null) {
        window.cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, activeCamera, fps, lastFrame]);

  const registerVideo = useCallback(
    (camera: string) => (element: HTMLVideoElement | null) => {
      const refs = videoRefs.current;
      if (element) {
        refs.set(camera, element);
        const target = currentFrame / fps;
        if (Math.abs(element.currentTime - target) > SYNC_DRIFT_SECONDS) {
          element.currentTime = target;
        }
      } else {
        refs.delete(camera);
      }
    },
    [currentFrame, fps]
  );

  const setCameraStatus = useCallback((camera: string, status: LoadStatus) => {
    setVideoStatus((current) => ({ ...current, [camera]: status }));
  }, []);

  const currentTimestampSeconds = currentFrame / fps;

  return (
    <main className="main-viewer">
      <div className="viewer-toolbar">
        <div>
          <div className="viewer-title">Episode #{episode.episodeIndex}</div>
          <div className="muted">
            {episode.caption || "(no caption)"} / {frameCount} frames / {fps} FPS
          </div>
        </div>
        <div className="toolbar-actions">
          <div className="layout-toggle" role="group" aria-label="Camera layout">
            <button
              className={`icon-button${layout === "focus" ? " active" : ""}`}
              onClick={() => setLayout("focus")}
              title="Focus on one camera"
              type="button"
            >
              <LayoutPanelLeft size={16} />
            </button>
            <button
              className={`icon-button${layout === "grid" ? " active" : ""}`}
              onClick={() => setLayout("grid")}
              title="Show all cameras"
              type="button"
            >
              <Grid2x2 size={16} />
            </button>
          </div>
          <button
            className="icon-button"
            onClick={() => setFrame(0)}
            title="Reset to first frame"
            type="button"
          >
            <RotateCcw size={16} />
          </button>
          <button className="icon-button" title="Fullscreen" type="button">
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      <section className={`camera-preview layout-${layout}`}>
        {layout === "focus" ? (
          <FocusCameras
            activeCamera={activeCamera}
            cameraNames={cameraNames}
            datasetId={episode.datasetId}
            episodeIndex={episode.episodeIndex}
            onSelectCamera={setActiveCamera}
            onStatusChange={setCameraStatus}
            registerVideo={registerVideo}
            videoStatus={videoStatus}
          />
        ) : (
          <GridCameras
            activeCamera={activeCamera}
            cameraNames={cameraNames}
            datasetId={episode.datasetId}
            episodeIndex={episode.episodeIndex}
            onSelectCamera={setActiveCamera}
            onStatusChange={setCameraStatus}
            registerVideo={registerVideo}
            videoStatus={videoStatus}
          />
        )}
      </section>

      <section className="playback-bar">
        <button
          className="icon-button"
          onClick={() => setFrame(currentFrame - JUMP_FRAMES)}
          title={`Jump back ${JUMP_FRAMES} frames`}
          type="button"
        >
          <SkipBack size={16} />
        </button>
        <button
          className="icon-button"
          onClick={() => setFrame(currentFrame - STEP_FRAMES)}
          title="Previous frame"
          type="button"
        >
          <span className="mono frame-step">−1</span>
        </button>
        <button
          className="primary-icon-button"
          onClick={handleTogglePlay}
          title={isPlaying ? "Pause" : "Play"}
          type="button"
        >
          {isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button
          className="icon-button"
          onClick={() => setFrame(currentFrame + STEP_FRAMES)}
          title="Next frame"
          type="button"
        >
          <span className="mono frame-step">+1</span>
        </button>
        <button
          className="icon-button"
          onClick={() => setFrame(currentFrame + JUMP_FRAMES)}
          title={`Jump forward ${JUMP_FRAMES} frames`}
          type="button"
        >
          <SkipForward size={16} />
        </button>
        <input
          aria-label="Frame scrubber"
          className="scrubber-input"
          max={lastFrame}
          min={0}
          onChange={(event) => setFrame(Number(event.target.value))}
          step={1}
          type="range"
          value={currentFrame}
        />
        <span className="scrubber-info mono">
          <span>{formatTime(currentTimestampSeconds)}</span>
          <span className="muted">/ {formatTime(lastFrame / fps)}</span>
          <span>
            f{currentFrame.toString().padStart(String(lastFrame).length, "0")}/{lastFrame}
          </span>
        </span>
      </section>

      <section className="state-action-panel">
        <NormPlot
          color="var(--accent)"
          dim={timeseries?.stateDim ?? null}
          frameCount={frameCount}
          markerFrame={currentFrame}
          status={timeseriesStatus}
          title="State norm"
          values={timeseries?.stateNorms ?? null}
          valueIndices={timeseries?.sampleIndices ?? null}
        />
        <NormPlot
          color="var(--blue)"
          dim={timeseries?.actionDim ?? null}
          frameCount={frameCount}
          markerFrame={currentFrame}
          status={timeseriesStatus}
          title="Action norm"
          values={timeseries?.actionNorms ?? null}
          valueIndices={timeseries?.sampleIndices ?? null}
        />
        <div className="state-action-meta">
          <span>{frameCount.toLocaleString()} frames</span>
          <span>
            {timeseriesStatus === "error"
              ? "timeseries unavailable"
              : timeseriesStatus === "loading"
                ? "loading timeseries"
                : `${timeseries?.sampleCount ?? 0} samples`}
          </span>
        </div>
      </section>
    </main>
  );
}

type CamerasGroupProps = {
  activeCamera: string;
  cameraNames: string[];
  datasetId: string;
  episodeIndex: number;
  onSelectCamera: (camera: string) => void;
  onStatusChange: (camera: string, status: LoadStatus) => void;
  registerVideo: (camera: string) => (element: HTMLVideoElement | null) => void;
  videoStatus: Record<string, LoadStatus>;
};

function FocusCameras({
  activeCamera,
  cameraNames,
  datasetId,
  episodeIndex,
  onSelectCamera,
  onStatusChange,
  registerVideo,
  videoStatus
}: CamerasGroupProps) {
  if (cameraNames.length === 0) {
    return (
      <div className="active-camera-stage">
        <div className="camera-pane-top">
          <span className="camera-name">No camera</span>
          <span className="camera-count">
            <Camera size={15} />0
          </span>
        </div>
        <div className="video-placeholder">
          <VideoMessage
            icon={<Camera size={18} />}
            label="No camera streams in episode metadata"
          />
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="active-camera-stage">
        <div className="camera-pane-top">
          <span className="camera-name" title={activeCamera}>
            {activeCamera}
          </span>
          <span className="camera-count">
            <Camera size={15} />
            {cameraNames.length}
          </span>
        </div>
        <div className="video-placeholder">
          {cameraNames.map((camera) => (
            <CameraVideo
              datasetId={datasetId}
              episodeIndex={episodeIndex}
              hidden={camera !== activeCamera}
              key={camera}
              name={camera}
              onStatusChange={onStatusChange}
              register={registerVideo(camera)}
              status={videoStatus[camera] ?? "idle"}
            />
          ))}
        </div>
      </div>
      <div className="camera-selector" aria-label="Camera selection">
        {cameraNames.map((camera) => {
          const isActive = camera === activeCamera;
          const status = videoStatus[camera] ?? "idle";
          return (
            <button
              className={`camera-select-button${isActive ? " active" : ""}`}
              key={camera}
              onClick={() => onSelectCamera(camera)}
              title={camera}
              type="button"
            >
              <span className="camera-select-name">{camera}</span>
              <span className={`camera-select-status camera-status-${status}`}>{status}</span>
            </button>
          );
        })}
      </div>
    </>
  );
}

function GridCameras({
  activeCamera,
  cameraNames,
  datasetId,
  episodeIndex,
  onSelectCamera,
  onStatusChange,
  registerVideo,
  videoStatus
}: CamerasGroupProps) {
  if (cameraNames.length === 0) {
    return (
      <div className="active-camera-stage">
        <div className="camera-pane-top">
          <span className="camera-name">No camera</span>
        </div>
        <div className="video-placeholder">
          <VideoMessage
            icon={<Camera size={18} />}
            label="No camera streams in episode metadata"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="camera-grid">
      {cameraNames.map((camera) => {
        const isLeader = camera === activeCamera;
        const status = videoStatus[camera] ?? "idle";
        return (
          <button
            className={`camera-grid-tile${isLeader ? " leader" : ""}`}
            key={camera}
            onClick={() => onSelectCamera(camera)}
            title={`Make ${camera} the playback leader`}
            type="button"
          >
            <span className="camera-grid-tile-top">
              <span className="camera-name">{camera}</span>
              <span className={`camera-select-status camera-status-${status}`}>{status}</span>
            </span>
            <span className="video-placeholder">
              <CameraVideo
                datasetId={datasetId}
                episodeIndex={episodeIndex}
                hidden={false}
                key={camera}
                name={camera}
                onStatusChange={onStatusChange}
                register={registerVideo(camera)}
                status={status}
              />
            </span>
          </button>
        );
      })}
    </div>
  );
}

type CameraVideoProps = {
  datasetId: string;
  episodeIndex: number;
  hidden: boolean;
  name: string;
  onStatusChange: (camera: string, status: LoadStatus) => void;
  register: (element: HTMLVideoElement | null) => void;
  status: LoadStatus;
};

function CameraVideo({
  datasetId,
  episodeIndex,
  hidden,
  name,
  onStatusChange,
  register,
  status
}: CameraVideoProps) {
  const src = useMemo(
    () => episodeVideoUrl(datasetId, episodeIndex, name),
    [datasetId, episodeIndex, name]
  );
  return (
    <>
      {status === "error" ? (
        <VideoMessage icon={<AlertTriangle size={18} />} label="Video stream failed to load" />
      ) : status !== "ready" ? (
        <VideoMessage icon={<Loader2 className="spin-icon" size={18} />} label="Loading video" />
      ) : null}
      <video
        className={`video-element${hidden ? " video-hidden" : ""}`}
        muted
        onCanPlay={() => onStatusChange(name, "ready")}
        onError={() => onStatusChange(name, "error")}
        playsInline
        preload="metadata"
        ref={register}
        src={src}
      />
    </>
  );
}

type NormPlotProps = {
  color: string;
  dim: number | null;
  frameCount: number;
  markerFrame: number;
  status: "loading" | "ready" | "error";
  title: string;
  values: (number | null)[] | null;
  valueIndices: number[] | null;
};

function NormPlot({
  color,
  dim,
  frameCount,
  markerFrame,
  status,
  title,
  values,
  valueIndices
}: NormPlotProps) {
  const dimText = dim === null ? "dim unknown" : `${dim} dim`;
  const points = useMemo(() => normalizePoints(values, valueIndices, frameCount), [
    values,
    valueIndices,
    frameCount
  ]);
  const markerX =
    frameCount > 1
      ? Math.max(0, Math.min(100, (markerFrame / (frameCount - 1)) * 100))
      : 0;

  return (
    <div className="plot-panel">
      <div className="plot-title-row">
        <span className="plot-title">{title}</span>
        <span className="plot-dim">{dimText}</span>
      </div>
      {status === "loading" ? (
        <div className="timeseries-empty">Loading timeseries</div>
      ) : status === "error" || !points ? (
        <div className="timeseries-empty">No numeric data</div>
      ) : (
        <svg
          aria-label={`${title} over frames`}
          className="timeseries-svg"
          preserveAspectRatio="none"
          viewBox="0 0 100 100"
        >
          <line
            className="timeseries-axis"
            x1={0}
            x2={100}
            y1={50}
            y2={50}
          />
          <polyline
            className="timeseries-line"
            points={points.polyline}
            style={{ stroke: color }}
          />
          <line
            className="timeseries-marker"
            x1={markerX}
            x2={markerX}
            y1={0}
            y2={100}
          />
        </svg>
      )}
      {points ? (
        <div className="plot-range muted mono">
          <span>min {formatNumber(points.min)}</span>
          <span>max {formatNumber(points.max)}</span>
        </div>
      ) : null}
    </div>
  );
}

function VideoMessage({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="video-message">
      {icon}
      <span>{label}</span>
    </span>
  );
}

type NormPoints = {
  polyline: string;
  min: number;
  max: number;
};

function normalizePoints(
  values: (number | null)[] | null,
  indices: number[] | null,
  frameCount: number
): NormPoints | null {
  if (!values || values.length === 0 || frameCount <= 0) {
    return null;
  }
  const cleaned: { x: number; y: number }[] = [];
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (value === null || Number.isNaN(value)) {
      continue;
    }
    const frameIndex = indices?.[i] ?? i;
    const x = frameCount > 1 ? (frameIndex / (frameCount - 1)) * 100 : 50;
    cleaned.push({ x, y: value });
    if (value < min) {
      min = value;
    }
    if (value > max) {
      max = value;
    }
  }
  if (cleaned.length === 0) {
    return null;
  }
  const range = max - min;
  const polyline = cleaned
    .map(({ x, y }) => {
      const normalized = range === 0 ? 50 : ((y - min) / range) * 92 + 4;
      const inverted = 100 - normalized;
      return `${x.toFixed(2)},${inverted.toFixed(2)}`;
    })
    .join(" ");
  return { polyline, min, max };
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "00:00.00";
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds - minutes * 60;
  return `${minutes.toString().padStart(2, "0")}:${remaining.toFixed(2).padStart(5, "0")}`;
}

function formatNumber(value: number) {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return Math.abs(value) >= 100 || Number.isInteger(value)
    ? value.toFixed(0)
    : value.toFixed(3);
}
