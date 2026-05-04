export type ReviewStatus = "pending" | "accepted" | "rejected" | "edited";

export type DatasetSummary = {
  datasetId: string;
  name: string;
  uri: string;
  status: string;
  episodeCount: number;
  frameCount: number;
  fps: number;
  cameraNames: string[];
  reviewedCount: number;
  acceptedCount: number;
  rejectedCount: number;
  message?: string | null;
};

export type Episode = {
  datasetId: string;
  episodeIndex: number;
  taskIndex: number;
  length: number;
  successLabel: boolean | null;
  qualityScore: number;
  reviewStatus: ReviewStatus;
  caption: string;
  failureReason: string;
  hasVlmLabel: boolean;
  hasHumanLabel: boolean;
  split: string;
  fps: number;
  cameraNames: string[];
};

export type StateActionSummary = {
  datasetId: string;
  episodeIndex: number;
  frameCount: number;
  stateDim: number | null;
  actionDim: number | null;
  stateNormMin: number | null;
  stateNormMax: number | null;
  actionNormMin: number | null;
  actionNormMax: number | null;
};

export type EpisodeTimeseries = {
  datasetId: string;
  episodeIndex: number;
  frameCount: number;
  fps: number | null;
  sampleCount: number;
  sampleIndices: number[];
  timestamps: (number | null)[] | null;
  stateNorms: (number | null)[];
  actionNorms: (number | null)[];
  stateDim: number | null;
  actionDim: number | null;
};

export type FrameLabel = {
  annotationId: string;
  labelType: string;
  labelValue: string;
  source: SegmentAnnotation["source"];
  confidence: number;
  reviewStatus: ReviewStatus;
};

export type FrameRecord = {
  datasetId: string;
  episodeIndex: number;
  frameIndex: number;
  timestamp: number | null;
  taskIndex: number | null;
  observationState: number[] | null;
  action: number[] | null;
  stateNorm: number | null;
  actionNorm: number | null;
  isBadFrame: boolean;
  labels: FrameLabel[];
};

export type SegmentAnnotation = {
  id: string;
  datasetId: string;
  episodeIndex: number;
  startFrame: number;
  endFrame: number;
  labelType: string;
  labelValue: string;
  source: "human" | "vlm" | "heuristic" | "import";
  confidence: number;
  reviewStatus: ReviewStatus;
};

export type RerunSession = {
  sessionId: string;
  datasetId: string;
  episodeIndex: number;
  mode: string;
  status: string;
  cacheKey: string | null;
  cacheHit: boolean;
  cameraCount: number;
  viewerUrl: string | null;
  rrdUrl: string | null;
  message: string | null;
};

export type JobRecord = {
  jobId: string;
  kind: string;
  status: string;
  datasetId: string;
  episodeIndices: number[];
  progress: number;
  message: string | null;
  createdAnnotationIds: string[];
  model: string | null;
  promptTemplate: string | null;
  promptVersion: string | null;
  provider: string | null;
  rawResponseIds: string[];
  rawResponseUri: string | null;
};

export type ExportRecord = {
  exportId: string;
  datasetId: string;
  episodeIndices: number[];
  format: string;
  status: string;
  outputUri: string | null;
  message: string | null;
  artifacts: ExportArtifacts | null;
};

export type ExportArtifacts = {
  lerobot_v3?: {
    root?: string;
    materialization_status?: string;
    validation?: {
      metadata_ok?: boolean;
      lerobot_loadable?: boolean;
      episode_count?: number;
      frame_count?: number;
      materialized_frame_count?: number;
      materialized_video_count?: number;
      errors?: string[];
      warnings?: string[];
    };
    files?: Record<string, string | null>;
    materialized?: {
      frame_rows?: number;
      video_files?: number;
    };
  };
  lance_subset?: {
    root?: string;
    validation?: {
      metadata_ok?: boolean;
      episode_count?: number;
      frame_count?: number;
      annotation_count?: number;
      errors?: string[];
      warnings?: string[];
    };
    files?: Record<string, string | null>;
    materialized?: {
      episode_rows?: number;
      frame_rows?: number;
      annotation_rows?: number;
    };
  };
};

export type SearchResult = {
  datasetId: string;
  episodeIndex: number;
  frameIndex: number | null;
  score: number | null;
  matchType: string;
  label: string | null;
};

export type FilterPreset = {
  presetId: string;
  datasetId: string;
  name: string;
  query: string;
  createdAt: string;
  updatedAt: string;
};
