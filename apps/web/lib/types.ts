export type ReviewStatus = "pending" | "accepted" | "rejected" | "edited";
export type ExportFormat = "lerobot" | "lance" | "jsonl" | "vla" | "hf_dataset";

export type DatasetSummary = {
  datasetId: string;
  name: string;
  uri: string;
  status: string;
  episodeCount: number;
  frameCount: number;
  fps: number;
  cameraNames: string[];
  cameraInfo: Record<string, Record<string, unknown>> | null;
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
  qualityScore: number | null;
  reviewStatus: ReviewStatus;
  caption: string;
  failureReason: string;
  hasVlmLabel: boolean;
  hasHumanLabel: boolean;
  split: string | null;
  fps: number;
  cameraNames: string[];
  languageInstruction: string | null;
};

export type EpisodeListPage = {
  datasetId: string;
  items: Episode[];
  total: number;
  limit: number;
  offset: number;
  nextOffset: number | null;
  previousOffset: number | null;
  sortBy: string;
  sortOrder: "asc" | "desc";
  filterQuery: string | null;
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

export type FrameListPage = {
  datasetId: string;
  episodeIndex: number;
  frameCount: number;
  startFrame: number;
  endFrame: number | null;
  limit: number;
  returnedCount: number;
  items: FrameRecord[];
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
  createdBy: string;
  assignedTo: string | null;
};

export type AnnotationHistoryRecord = {
  eventId: string;
  datasetId: string;
  annotationId: string;
  episodeIndex: number;
  action: "create" | "update" | "delete" | string;
  actor: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  createdAt: string;
};

export type EpisodeLabelHistoryRecord = {
  eventId: string;
  datasetId: string;
  episodeIndex: number;
  action: "update" | string;
  actor: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  createdAt: string;
};

export type UserIdentity = {
  userId: string;
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
  publishedUri: string | null;
  publishSizeBytes: number | null;
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
  createdEmbeddingIds: string[];
  artifactCount: number;
  createdExportId: string | null;
  exportFormat: string | null;
  exportUri: string | null;
  createdRerunSessionId: string | null;
  rerunRrdUrl: string | null;
  rerunRrdPath: string | null;
  rerunPublishedUri: string | null;
  rerunViewerUrl: string | null;
  queueJobId: string | null;
};

export type VlmResponseRecord = {
  responseId: string;
  datasetId: string;
  jobId: string;
  episodeIndex: number;
  provider: string;
  createdAt: string;
  rawResponse: Record<string, unknown>;
};

export type JobProgressEvent = {
  jobId: string;
  kind: string;
  status: string;
  progress: number;
  message: string | null;
  queueJobId: string | null;
  rawResponseIds: string[];
  rawResponseUri: string | null;
  createdExportId: string | null;
  exportFormat: string | null;
  exportUri: string | null;
  createdRerunSessionId: string | null;
  rerunRrdUrl: string | null;
  rerunRrdPath: string | null;
  rerunPublishedUri: string | null;
  rerunViewerUrl: string | null;
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
      loadability_basis?: string;
      local_lerobot_loadable_heuristic?: boolean;
      official_loader?: {
        checked?: boolean;
        available?: boolean;
        ok?: boolean | null;
        repo_id?: string | null;
        root?: string | null;
        error?: string | null;
        error_chain?: string[];
        length?: number | null;
      };
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
  jsonl?: JsonlExportArtifact;
  vla_jsonl?: JsonlExportArtifact;
  hf_dataset?: JsonlExportArtifact & {
    validation?: {
      metadata_ok?: boolean;
      loadable?: boolean;
      frame_count?: number;
      errors?: string[];
      warnings?: string[];
    };
  };
};

export type JsonlExportArtifact = {
  root?: string;
  files?: Record<string, string | null>;
  materialized?: Record<string, number | undefined>;
};

export type SearchResult = {
  datasetId: string;
  episodeIndex: number;
  frameIndex: number | null;
  score: number | null;
  matchType: string;
  label: string | null;
  modality: string | null;
  sourceModel: string | null;
  camera: string | null;
  sourceUri: string | null;
};

export type FilterPreset = {
  presetId: string;
  datasetId: string;
  name: string;
  query: string;
  createdAt: string;
  updatedAt: string;
};
