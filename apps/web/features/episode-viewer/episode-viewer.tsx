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
  Activity,
  AlertTriangle,
  Camera,
  Grid2x2,
  LayoutPanelLeft,
  Loader2,
  Maximize2,
  Pause,
  Play,
  Rows3,
  RotateCcw,
  SkipBack,
  SkipForward
} from "lucide-react";

import { episodePreviewUrl, episodeVideoUrl, fetchEpisodeTimeseries } from "@/lib/api";
import type { Episode, EpisodeTimeseries, SegmentAnnotation, TaskSegment } from "@/lib/types";
import { HUMANOID_SIGNAL_PRESETS, type SignalPreset } from "./signal-presets";

type EpisodeViewerProps = {
  annotations: SegmentAnnotation[];
  episode: Episode;
  onFrameChange: (frameIndex: number) => void;
  selectedFrame: number;
  onToggleSignals?: () => void;
  showSignals?: boolean;
  enableInternalKeymap?: boolean;
  initialLayout?: "focus" | "grid" | "stack";
};

type CameraLayout = "focus" | "grid" | "stack";
type LoadStatus = "idle" | "ready" | "error";
type PlotChannel = "norm" | number;

const SYNC_DRIFT_SECONDS = 0.08;
const STEP_FRAMES = 1;
const JUMP_FRAMES = 30;

export function EpisodeViewer({
  annotations,
  episode,
  onFrameChange,
  selectedFrame,
  onToggleSignals,
  showSignals = false,
  enableInternalKeymap = true,
  initialLayout = "focus"
}: EpisodeViewerProps) {
  const cameraNames = episode.cameraNames;
  const fps = episode.fps > 0 ? episode.fps : 20;
  const frameCount = Math.max(1, episode.length || 0);
  const lastFrame = Math.max(0, frameCount - 1);

  const [layout, setLayout] = useState<CameraLayout>(initialLayout);
  const [activeCamera, setActiveCamera] = useState<string>(cameraNames[0] ?? "");
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [stateChannel, setStateChannel] = useState<PlotChannel>("norm");
  const [actionChannel, setActionChannel] = useState<PlotChannel>("norm");
  const [videoStatus, setVideoStatus] = useState<Record<string, LoadStatus>>({});
  const [timeseries, setTimeseries] = useState<EpisodeTimeseries | null>(null);
  const [timeseriesStatus, setTimeseriesStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const [activePreset, setActivePreset] = useState<string>("overview");
  const [enlargedCamera, setEnlargedCamera] = useState<string | null>(null);
  const taskSegments = useMemo(
    () => normalizeTaskSegments(episode.taskSegments ?? [], frameCount),
    [episode.taskSegments, frameCount]
  );
  const activeTaskSegment = useMemo(
    () =>
      taskSegments.find(
        (segment) =>
          currentFrame >= segment.startFrame && currentFrame < segment.endFrameExclusive
      ) ?? null,
    [currentFrame, taskSegments]
  );

  // Esc to close per-camera enlarge overlay (without triggering native
  // requestFullscreen exit). Only attached when something is enlarged.
  useEffect(() => {
    if (!enlargedCamera) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setEnlargedCamera(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enlargedCamera]);

  const videoRefs = useRef<Map<string, HTMLVideoElement>>(new Map());
  const animationRef = useRef<number | null>(null);
  const currentFrameRef = useRef(0);
  const stageRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!enableInternalKeymap) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      if (isTyping) {
        return;
      }

      if (event.code === "Space") {
        event.preventDefault();
        setIsPlaying((current) => !current);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enableInternalKeymap]);

  useEffect(() => {
    currentFrameRef.current = currentFrame;
  }, [currentFrame]);

  useEffect(() => {
    setActiveCamera((current) =>
      current && cameraNames.includes(current) ? current : cameraNames[0] ?? ""
    );
  }, [cameraNames]);

  useEffect(() => {
    currentFrameRef.current = 0;
    setCurrentFrame(0);
    onFrameChange(0);
    setIsPlaying(false);
    setVideoStatus({});
  }, [episode.datasetId, episode.episodeIndex, onFrameChange]);

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
      currentFrameRef.current = clamped;
      setCurrentFrame(clamped);
      onFrameChange(clamped);
      seekVideosToFrame(clamped);
    },
    [lastFrame, onFrameChange, seekVideosToFrame]
  );

  useEffect(() => {
    const clamped = Math.max(0, Math.min(lastFrame, Math.round(selectedFrame)));
    currentFrameRef.current = clamped;
    setCurrentFrame((current) => (current === clamped ? current : clamped));
    seekVideosToFrame(clamped);
  }, [lastFrame, seekVideosToFrame, selectedFrame]);

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
        if (currentFrameRef.current !== frame) {
          currentFrameRef.current = frame;
          setCurrentFrame(frame);
          onFrameChange(frame);
        }
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
  }, [isPlaying, activeCamera, fps, lastFrame, onFrameChange]);

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
    <main className="main-viewer" ref={stageRef}>
      <div className="viewer-toolbar">
        <div className="muted viewer-meta">
          {frameCount} frames · {fps} FPS
          {activeTaskSegment ? (
            <>
              {" · "}
              {taskSegmentLabel(activeTaskSegment)}
            </>
          ) : null}
        </div>
        <div className="toolbar-actions">
          {onToggleSignals ? (
            <button
              className={`icon-button${showSignals ? " active" : ""}`}
              onClick={onToggleSignals}
              title={showSignals ? "Hide state/action signals" : "Show state/action signals"}
              type="button"
            >
              <Activity size={16} />
            </button>
          ) : null}
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
              title="Show all cameras (grid)"
              type="button"
            >
              <Grid2x2 size={16} />
            </button>
            <button
              className={`icon-button${layout === "stack" ? " active" : ""}`}
              onClick={() => setLayout("stack")}
              title="Stack: main on top, secondaries below"
              type="button"
            >
              <Rows3 size={16} />
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
          <button 
            className="icon-button" 
            onClick={() => stageRef.current?.requestFullscreen()}
            title="Fullscreen" 
            type="button"
          >
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
            enlargedCamera={enlargedCamera}
            onEnlargeCamera={setEnlargedCamera}
            onSelectCamera={setActiveCamera}
            onStatusChange={setCameraStatus}
            registerVideo={registerVideo}
            videoStatus={videoStatus}
          />
        ) : layout === "stack" ? (
          <StackCameras
            activeCamera={activeCamera}
            cameraNames={cameraNames}
            datasetId={episode.datasetId}
            episodeIndex={episode.episodeIndex}
            enlargedCamera={enlargedCamera}
            onEnlargeCamera={setEnlargedCamera}
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
            enlargedCamera={enlargedCamera}
            onEnlargeCamera={setEnlargedCamera}
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

      {taskSegments.length > 0 ? (
        <TaskSegmentStrip
          activeFrame={currentFrame}
          frameCount={frameCount}
          onSelectFrame={setFrame}
          segments={taskSegments}
        />
      ) : null}

      {showSignals ? (
        <section className="state-action-panel">
          <div className="frame-quick-labels" style={{ marginBottom: "8px" }}>
            {HUMANOID_SIGNAL_PRESETS.map((preset: SignalPreset) => (
              <button
                key={preset.id}
                className={`quick-label-button${activePreset === preset.id ? " active" : ""}`}
                onClick={() => {
                  setActivePreset(preset.id);
                  if (preset.stateChannels.length > 0) {
                    setStateChannel(preset.stateChannels[0]);
                  } else {
                    setStateChannel("norm");
                  }
                  if (preset.actionChannels.length > 0) {
                    setActionChannel(preset.actionChannels[0]);
                  } else {
                    setActionChannel("norm");
                  }
                }}
                type="button"
              >
                {preset.label}
              </button>
            ))}
          </div>
          <SignalPlot
            annotations={annotations}
            channel={stateChannel}
            color="var(--accent)"
            dim={timeseries?.stateDim ?? null}
            frameCount={frameCount}
            markerFrame={currentFrame}
            onChannelChange={setStateChannel}
            status={timeseriesStatus}
            title="State"
            vectorValues={timeseries?.stateValues ?? null}
            normValues={timeseries?.stateNorms ?? null}
            valueIndices={timeseries?.sampleIndices ?? null}
          />
          <SignalPlot
            annotations={annotations}
            channel={actionChannel}
            color="var(--blue)"
            dim={timeseries?.actionDim ?? null}
            frameCount={frameCount}
            markerFrame={currentFrame}
            onChannelChange={setActionChannel}
            status={timeseriesStatus}
            title="Action"
            vectorValues={timeseries?.actionValues ?? null}
            normValues={timeseries?.actionNorms ?? null}
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
      ) : null}
    </main>
  );
}

function TaskSegmentStrip({
  activeFrame,
  frameCount,
  onSelectFrame,
  segments
}: {
  activeFrame: number;
  frameCount: number;
  onSelectFrame: (frame: number) => void;
  segments: TaskSegment[];
}) {
  const denominator = Math.max(1, frameCount);
  return (
    <section className="task-segment-strip" aria-label="Task segments">
      {segments.map((segment, index) => {
        const start = Math.max(0, Math.min(frameCount, segment.startFrame));
        const end = Math.max(start + 1, Math.min(frameCount, segment.endFrameExclusive));
        const isActive = activeFrame >= start && activeFrame < end;
        const left = (start / denominator) * 100;
        const width = Math.max(0.75, ((end - start) / denominator) * 100);
        return (
          <button
            className={`task-segment-chip${isActive ? " active" : ""}`}
            key={`${segment.taskIndex ?? "task"}-${start}-${end}-${index}`}
            onClick={() => onSelectFrame(start)}
            style={{ left: `${left}%`, width: `${width}%` }}
            title={`${taskSegmentLabel(segment)} · f${start}-${end}`}
            type="button"
          >
            <span>{taskSegmentLabel(segment)}</span>
            <small className="mono">
              [{start},{end})
            </small>
          </button>
        );
      })}
    </section>
  );
}

type CamerasGroupProps = {
  activeCamera: string;
  cameraNames: string[];
  datasetId: string;
  episodeIndex: number;
  enlargedCamera: string | null;
  onEnlargeCamera: (camera: string | null) => void;
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
  enlargedCamera: _enlargedCamera,
  onEnlargeCamera: _onEnlargeCamera,
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
          <div className="camera-tabs" aria-label="Camera selection">
            {cameraNames.map((camera) => {
              const isActive = camera === activeCamera;
              const status = videoStatus[camera] ?? "idle";
              return (
                <button
                  className={`camera-tab${isActive ? " active" : ""}`}
                  key={camera}
                  onClick={() => onSelectCamera(camera)}
                  title={camera}
                  type="button"
                >
                  <span>{shortCameraName(camera)}</span>
                  <span className={`camera-tab-dot camera-status-${status}`} />
                </button>
              );
            })}
          </div>
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
    </>
  );
}

function GridCameras({
  activeCamera,
  cameraNames,
  datasetId,
  episodeIndex,
  enlargedCamera,
  onEnlargeCamera,
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

  // Leader takes the large left column at full height; the remaining cameras
  // stack on the right at half-height each (NLE picture-in-picture style).
  const leaderCamera =
    cameraNames.includes(activeCamera) ? activeCamera : cameraNames[0];
  const secondaryCameras = cameraNames.filter((camera) => camera !== leaderCamera);
  const orderedCameras = [leaderCamera, ...secondaryCameras];

  return (
    <div
      className={`camera-grid grid-secondary-${secondaryCameras.length}${enlargedCamera ? " has-enlarged" : ""}`}
    >
      {orderedCameras.map((camera) => {
        const isLeader = camera === leaderCamera;
        const status = videoStatus[camera] ?? "idle";
        return (
          <CameraTile
            camera={camera}
            className={`camera-grid-tile${isLeader ? " leader" : ""}`}
            datasetId={datasetId}
            enlarged={enlargedCamera === camera}
            episodeIndex={episodeIndex}
            key={camera}
            onEnlargeCamera={onEnlargeCamera}
            onSelectCamera={onSelectCamera}
            onStatusChange={onStatusChange}
            registerVideo={registerVideo}
            status={status}
          />
        );
      })}
      {enlargedCamera ? (
        <div
          className="camera-enlarge-scrim"
          onClick={() => onEnlargeCamera(null)}
          aria-label="Close enlarged camera"
        />
      ) : null}
    </div>
  );
}

function StackCameras({
  activeCamera,
  cameraNames,
  datasetId,
  episodeIndex,
  enlargedCamera,
  onEnlargeCamera,
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

  // Vertical stack: leader on top, secondary cameras share a single row beneath.
  // Compact triage layout — leaves room for charts / actions below the stack.
  const leaderCamera =
    cameraNames.includes(activeCamera) ? activeCamera : cameraNames[0];
  const secondaryCameras = cameraNames.filter((camera) => camera !== leaderCamera);

  return (
    <div
      className={`camera-stack secondary-${secondaryCameras.length}${enlargedCamera ? " has-enlarged" : ""}`}
    >
      <CameraTile
        camera={leaderCamera}
        className="camera-stack-leader camera-grid-tile leader"
        datasetId={datasetId}
        enlarged={enlargedCamera === leaderCamera}
        episodeIndex={episodeIndex}
        onEnlargeCamera={onEnlargeCamera}
        onSelectCamera={onSelectCamera}
        onStatusChange={onStatusChange}
        registerVideo={registerVideo}
        status={videoStatus[leaderCamera] ?? "idle"}
      />
      {secondaryCameras.length > 0 ? (
        <div className="camera-stack-secondary">
          {secondaryCameras.map((camera) => (
            <CameraTile
              camera={camera}
              className="camera-grid-tile"
              datasetId={datasetId}
              enlarged={enlargedCamera === camera}
              episodeIndex={episodeIndex}
              key={camera}
              onEnlargeCamera={onEnlargeCamera}
              onSelectCamera={onSelectCamera}
              onStatusChange={onStatusChange}
              registerVideo={registerVideo}
              status={videoStatus[camera] ?? "idle"}
            />
          ))}
        </div>
      ) : null}
      {enlargedCamera ? (
        <div
          className="camera-enlarge-scrim"
          onClick={() => onEnlargeCamera(null)}
          aria-label="Close enlarged camera"
        />
      ) : null}
    </div>
  );
}

type CameraTileProps = {
  camera: string;
  className: string;
  datasetId: string;
  enlarged: boolean;
  episodeIndex: number;
  onEnlargeCamera: (camera: string | null) => void;
  onSelectCamera: (camera: string) => void;
  onStatusChange: (camera: string, status: LoadStatus) => void;
  registerVideo: (camera: string) => (element: HTMLVideoElement | null) => void;
  status: LoadStatus;
};

function CameraTile({
  camera,
  className,
  datasetId,
  enlarged,
  episodeIndex,
  onEnlargeCamera,
  onSelectCamera,
  onStatusChange,
  registerVideo,
  status
}: CameraTileProps) {
  return (
    <div
      className={`${className}${enlarged ? " is-enlarged" : ""}`}
      onClick={() => {
        if (enlarged) return;
        onSelectCamera(camera);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (enlarged) onEnlargeCamera(null);
          else onSelectCamera(camera);
        }
      }}
      role="button"
      tabIndex={0}
      title={enlarged ? "Click outside or press Esc to close" : `Make ${camera} the playback leader`}
    >
      <span className="camera-grid-tile-top">
        <span className="camera-name">{camera}</span>
        <span className={`camera-select-status camera-status-${status}`}>{status}</span>
        <button
          type="button"
          className="camera-enlarge-btn"
          onClick={(event) => {
            event.stopPropagation();
            onEnlargeCamera(enlarged ? null : camera);
          }}
          title={enlarged ? "Exit enlarge (Esc)" : "Enlarge this camera"}
          aria-label={enlarged ? "Close enlarged camera" : `Enlarge ${camera}`}
        >
          <Maximize2 size={12} />
        </button>
      </span>
      <span className="video-placeholder">
        <CameraVideo
          datasetId={datasetId}
          episodeIndex={episodeIndex}
          hidden={false}
          name={camera}
          onStatusChange={onStatusChange}
          register={registerVideo(camera)}
          status={status}
        />
      </span>
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
  const poster = useMemo(
    () => episodePreviewUrl(datasetId, episodeIndex, name),
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
        poster={poster}
        preload="metadata"
        ref={register}
        src={src}
      />
    </>
  );
}

type NormPlotProps = {
  annotations: SegmentAnnotation[];
  channel: PlotChannel;
  color: string;
  dim: number | null;
  frameCount: number;
  markerFrame: number;
  onChannelChange: (channel: PlotChannel) => void;
  status: "loading" | "ready" | "error";
  title: string;
  vectorValues: ((number | null)[] | null)[] | null;
  normValues: (number | null)[] | null;
  valueIndices: number[] | null;
};

function SignalPlot({
  annotations,
  channel,
  color,
  dim,
  frameCount,
  markerFrame,
  onChannelChange,
  status,
  title,
  vectorValues,
  normValues,
  valueIndices
}: NormPlotProps) {
  const dimText = dim === null ? "dim unknown" : `${dim} dim`;
  const values = useMemo(
    () => valuesForChannel(channel, normValues, vectorValues),
    [channel, normValues, vectorValues]
  );
  const points = useMemo(() => normalizePoints(values, valueIndices, frameCount), [
    values,
    valueIndices,
    frameCount
  ]);
  const annotationBands = useMemo(
    () => annotationsToBands(annotations, frameCount),
    [annotations, frameCount]
  );
  const markerX =
    frameCount > 1
      ? Math.max(0, Math.min(100, (markerFrame / (frameCount - 1)) * 100))
      : 0;
  const activeValue = points ? valueAtFrame(values, valueIndices, markerFrame) : null;

  return (
    <div className="plot-panel">
      <div className="plot-title-row">
        <div className="plot-heading">
          <span className="plot-title">{title}</span>
          <span className="plot-dim">{dimText}</span>
        </div>
        <select
          aria-label={`${title} channel`}
          className="plot-channel-select"
          onChange={(event) => {
            const next = event.target.value;
            onChannelChange(next === "norm" ? "norm" : Number(next));
          }}
          value={String(channel)}
        >
          <option value="norm">norm</option>
          {Array.from({ length: Math.max(0, dim ?? 0) }, (_, index) => (
            <option key={index} value={index}>
              dim {index}
            </option>
          ))}
        </select>
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
          {annotationBands.map((band) => (
            <rect
              className={`timeseries-annotation-band band-${band.reviewStatus} label-${band.labelType}`}
              height={100}
              key={band.id}
              width={band.width}
              x={band.x}
              y={0}
            />
          ))}
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
          <span>now {formatMaybeNumber(activeValue)}</span>
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

type AnnotationBand = {
  id: string;
  labelType: string;
  reviewStatus: SegmentAnnotation["reviewStatus"];
  width: number;
  x: number;
};

function valuesForChannel(
  channel: PlotChannel,
  normValues: (number | null)[] | null,
  vectorValues: ((number | null)[] | null)[] | null
): (number | null)[] | null {
  if (channel === "norm") {
    return normValues;
  }
  if (!vectorValues || vectorValues.length === 0) {
    return null;
  }
  return vectorValues.map((vector) => vector?.[channel] ?? null);
}

function annotationsToBands(annotations: SegmentAnnotation[], frameCount: number): AnnotationBand[] {
  if (frameCount <= 1) {
    return [];
  }
  return annotations
    .filter((annotation) => annotation.reviewStatus !== "rejected")
    .map((annotation) => {
      const start = Math.max(0, Math.min(frameCount - 1, annotation.startFrame));
      const end = Math.max(start, Math.min(frameCount - 1, annotation.endFrame));
      const x = (start / (frameCount - 1)) * 100;
      const width = Math.max(0.35, ((end - start + 1) / frameCount) * 100);
      return {
        id: annotation.id,
        labelType: annotation.labelType,
        reviewStatus: annotation.reviewStatus,
        width,
        x
      };
    });
}

function valueAtFrame(
  values: (number | null)[] | null,
  indices: number[] | null,
  frame: number
): number | null {
  if (!values || values.length === 0) {
    return null;
  }
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < values.length; index += 1) {
    const sampleFrame = indices?.[index] ?? index;
    const distance = Math.abs(sampleFrame - frame);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }
  return values[bestIndex] ?? null;
}

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

function normalizeTaskSegments(segments: TaskSegment[], frameCount: number): TaskSegment[] {
  if (!segments || frameCount <= 0) {
    return [];
  }
  return segments
    .map((segment) => {
      const startFrame = Math.max(0, Math.min(frameCount - 1, Math.floor(segment.startFrame)));
      const endFrameExclusive = Math.max(
        startFrame + 1,
        Math.min(frameCount, Math.ceil(segment.endFrameExclusive))
      );
      return {
        ...segment,
        startFrame,
        endFrameExclusive
      };
    })
    .filter((segment) => segment.endFrameExclusive > segment.startFrame)
    .sort((a, b) => a.startFrame - b.startFrame);
}

function taskSegmentLabel(segment: TaskSegment): string {
  const text = segment.languageInstruction?.trim();
  if (text) {
    return text;
  }
  return segment.taskIndex === null ? "task" : `task ${segment.taskIndex}`;
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

function formatMaybeNumber(value: number | null) {
  return value === null ? "—" : formatNumber(value);
}

function shortCameraName(name: string): string {
  return name
    .replace(/^observation\.images\./, "")
    .replace(/^observation_images_/, "")
    .replace(/^camera_/, "");
}
