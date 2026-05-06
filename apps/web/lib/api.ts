import type {
  AnnotationHistoryRecord,
  DatasetHealth,
  DatasetSummary,
  DatasetTableHealth,
  Episode,
  EpisodeLabelHistoryRecord,
  EpisodeListPage,
  EpisodeTimeseries,
  ExportFormat,
  ExportRecord,
  SkillExportOptions,
  FilterPreset,
  FrameListPage,
  FrameRecord,
  JobProgressEvent,
  JobRecord,
  RerunSession,
  ReviewStatus,
  SearchResult,
  SegmentAnnotation,
  StateActionSummary,
  UserIdentity,
  VlmResponseRecord
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const API_ROOT_URL = API_BASE_URL.endsWith("/api")
  ? API_BASE_URL.slice(0, -"/api".length)
  : API_BASE_URL;
const VLM_MODEL = process.env.NEXT_PUBLIC_VLM_MODEL ?? "heuristic-vlm-fallback";
const VLM_PROMPT_TEMPLATE = process.env.NEXT_PUBLIC_VLM_PROMPT_TEMPLATE ?? "episode_autolabel_v1";
const VLM_MIN_KEYFRAMES = Number(process.env.NEXT_PUBLIC_VLM_MIN_KEYFRAMES ?? "8");
const VLM_MAX_KEYFRAMES = Number(process.env.NEXT_PUBLIC_VLM_MAX_KEYFRAMES ?? "16");
const API_KEY = process.env.NEXT_PUBLIC_ROBOT_DATA_STUDIO_API_KEY ?? "";
const REVIEW_USER = process.env.NEXT_PUBLIC_ROBOT_DATA_STUDIO_USER ?? "";

export class ApiConflictError extends Error {
  status = 409;

  constructor(message: string) {
    super(message);
    this.name = "ApiConflictError";
  }
}

type DatasetRecordResponse = {
  dataset_id: string;
  name: string;
  uri: string;
  status: string;
  message?: string | null;
};

type DatasetSummaryResponse = DatasetRecordResponse & {
  episode_count: number;
  frame_count: number;
  fps: number | null;
  camera_names: string[];
  camera_info?: Record<string, Record<string, unknown>> | null;
  reviewed_count: number;
  accepted_count: number;
  rejected_count: number;
};

type DatasetTableHealthResponse = {
  table: string;
  present: boolean;
  row_count: number | null;
  columns: string[];
  missing_required_columns: string[];
  warnings: string[];
};

type DatasetHealthResponse = {
  dataset_id: string;
  ok: boolean;
  status: string;
  storage_model: string;
  level?: string;
  episode_count: number;
  frame_count: number;
  camera_count: number;
  tables: DatasetTableHealthResponse[];
  warnings: string[];
  errors: string[];
};

type EpisodeResponse = {
  dataset_id: string;
  episode_index: number;
  task_index: number | null;
  length: number | null;
  success_label: boolean | null;
  failure_reason: string | null;
  quality_score: number | null;
  review_status: Episode["reviewStatus"];
  caption: string | null;
  has_vlm_label: boolean;
  has_human_label: boolean;
  split: string | null;
  fps?: number | null;
  camera_names?: string[];
  language_instruction?: string | null;
};

type EpisodeListPageResponse = {
  dataset_id: string;
  items: EpisodeResponse[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  previous_offset: number | null;
  sort_by: string;
  sort_order: "asc" | "desc";
  filter_query: string | null;
};

type AnnotationResponse = {
  annotation_id: string;
  dataset_id: string;
  episode_index: number;
  start_frame: number;
  end_frame: number;
  label_type: string;
  label_value: string;
  source: SegmentAnnotation["source"];
  confidence: number;
  review_status: ReviewStatus;
  metadata?: Record<string, unknown> | null;
  created_by: string;
  updated_by?: string | null;
  assigned_to: string | null;
  revision?: number | null;
  deleted_at?: string | null;
  lock_owner?: string | null;
  lock_expires_at?: string | null;
};

type AnnotationHistoryResponse = {
  event_id: string;
  dataset_id: string;
  annotation_id: string;
  episode_index: number;
  action: string;
  actor: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

type EpisodeLabelHistoryResponse = {
  event_id: string;
  dataset_id: string;
  episode_index: number;
  action: string;
  actor: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

type UserIdentityResponse = {
  user_id: string;
};

type RerunSessionResponse = {
  session_id: string;
  dataset_id: string;
  episode_index: number;
  mode: string;
  status: string;
  cache_key: string | null;
  cache_hit: boolean;
  camera_count: number;
  viewer_url: string | null;
  rrd_url: string | null;
  published_uri: string | null;
  publish_size_bytes: number | null;
  message: string | null;
};

type JobRecordResponse = {
  job_id: string;
  kind: string;
  status: string;
  dataset_id: string;
  episode_indices: number[];
  progress: number;
  message: string | null;
  created_annotation_ids: string[];
  model: string | null;
  prompt_template: string | null;
  prompt_version: string | null;
  provider: string | null;
  raw_response_ids: string[];
  raw_response_uri: string | null;
  created_embedding_ids: string[];
  artifact_count: number;
  created_export_id: string | null;
  export_format: string | null;
  export_uri: string | null;
  created_rerun_session_id: string | null;
  rerun_rrd_url: string | null;
  rerun_rrd_path: string | null;
  rerun_published_uri: string | null;
  rerun_viewer_url: string | null;
  queue_job_id: string | null;
};

type JobProgressEventResponse = {
  job_id: string;
  kind: string;
  status: string;
  progress: number;
  message: string | null;
  queue_job_id: string | null;
  raw_response_ids: string[];
  raw_response_uri: string | null;
  created_export_id: string | null;
  export_format: string | null;
  export_uri: string | null;
  created_rerun_session_id: string | null;
  rerun_rrd_url: string | null;
  rerun_rrd_path: string | null;
  rerun_published_uri: string | null;
  rerun_viewer_url: string | null;
};

type VlmResponseRecordResponse = {
  response_id: string;
  dataset_id: string;
  job_id: string;
  episode_index: number;
  provider: string;
  created_at: string;
  raw_response: Record<string, unknown>;
};

type ExportRecordResponse = {
  export_id: string;
  dataset_id: string;
  episode_indices: number[];
  format: string;
  status: string;
  output_uri: string | null;
  message: string | null;
  artifacts?: ExportRecord["artifacts"];
};

type SearchResultResponse = {
  dataset_id: string;
  episode_index: number;
  frame_index: number | null;
  score: number | null;
  match_type: string;
  label: string | null;
  modality?: string | null;
  source_model?: string | null;
  camera?: string | null;
  source_uri?: string | null;
};

type FilterPresetResponse = {
  preset_id: string;
  dataset_id: string;
  name: string;
  query: string;
  created_at: string;
  updated_at: string;
};

type StateActionSummaryResponse = {
  dataset_id: string;
  episode_index: number;
  frame_count: number;
  state_dim: number | null;
  action_dim: number | null;
  state_norm_min: number | null;
  state_norm_max: number | null;
  action_norm_min: number | null;
  action_norm_max: number | null;
};

type EpisodeTimeseriesResponse = {
  dataset_id: string;
  episode_index: number;
  frame_count: number;
  fps: number | null;
  sample_count: number;
  sample_indices: number[];
  timestamps: (number | null)[] | null;
  state_norms: (number | null)[];
  action_norms: (number | null)[];
  state_values: ((number | null)[] | null)[];
  action_values: ((number | null)[] | null)[];
  state_dim: number | null;
  action_dim: number | null;
};

type FrameLabelResponse = {
  annotation_id: string;
  label_type: string;
  label_value: string;
  source: SegmentAnnotation["source"];
  confidence: number;
  review_status: ReviewStatus;
};

type FrameRecordResponse = {
  dataset_id: string;
  episode_index: number;
  frame_index: number;
  timestamp: number | null;
  task_index: number | null;
  observation_state: number[] | null;
  action: number[] | null;
  state_norm: number | null;
  action_norm: number | null;
  is_bad_frame: boolean;
  labels: FrameLabelResponse[];
};

type FrameListResponse = {
  dataset_id: string;
  episode_index: number;
  frame_count: number;
  start_frame: number;
  end_frame: number | null;
  limit: number;
  returned_count: number;
  items: FrameRecordResponse[];
};

export type SegmentAnnotationCreate = {
  datasetId: string;
  episodeIndex: number;
  startFrame: number;
  endFrame: number;
  labelType: string;
  labelValue: string;
  source?: SegmentAnnotation["source"];
  confidence?: number;
  reviewStatus?: ReviewStatus;
  metadata?: SegmentAnnotation["metadata"];
};

export type SegmentAnnotationUpdate = {
  startFrame?: number;
  endFrame?: number;
  labelType?: string;
  labelValue?: string;
  reviewStatus?: ReviewStatus;
  assignedTo?: string | null;
  expectedRevision?: number;
  metadata?: SegmentAnnotation["metadata"];
};

export type EpisodeLabelUpdate = {
  caption?: string | null;
  successLabel?: boolean | null;
  failureReason?: string | null;
  qualityScore?: number | null;
  split?: string | null;
  reviewStatus?: ReviewStatus | null;
  languageInstruction?: string | null;
};

export type FrameUpdate = {
  isBadFrame?: boolean | null;
  labelType?: string | null;
  labelValue?: string | null;
  labelEnabled?: boolean | null;
};

export async function fetchDatasetSummaries(): Promise<DatasetSummary[]> {
  const datasets = await request<DatasetRecordResponse[]>("/datasets");
  return Promise.all(datasets.map((dataset) => fetchDatasetSummary(dataset.dataset_id)));
}

export async function fetchDatasetSummary(datasetId: string): Promise<DatasetSummary> {
  return request<DatasetSummaryResponse>(`/datasets/${datasetId}/summary`).then(toDatasetSummary);
}

export async function fetchDatasetHealth(
  datasetId: string,
  level: "shallow" | "deep" = "shallow",
): Promise<DatasetHealth> {
  const query = new URLSearchParams({ level });
  return request<DatasetHealthResponse>(`/datasets/${datasetId}/health?${query}`).then(toDatasetHealth);
}

export type EpisodeListOptions = {
  limit?: number;
  offset?: number;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  filterQuery?: string;
};

function episodeListQuery(datasetId: string, options: EpisodeListOptions = {}): string {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    limit: String(options.limit ?? 200),
    offset: String(options.offset ?? 0),
    sort_by: options.sortBy ?? "episode_index",
    sort_order: options.sortOrder ?? "asc"
  });
  if (options.filterQuery) {
    query.set("filter_query", options.filterQuery);
  }
  return query.toString();
}

export async function fetchEpisodes(
  datasetId: string,
  options: EpisodeListOptions = {}
): Promise<Episode[]> {
  const episodes = await request<EpisodeResponse[]>(
    `/episodes?${episodeListQuery(datasetId, options)}`
  );
  return episodes.map(toEpisode);
}

export async function fetchEpisodePage(
  datasetId: string,
  options: EpisodeListOptions = {}
): Promise<EpisodeListPage> {
  return request<EpisodeListPageResponse>(`/episodes/page?${episodeListQuery(datasetId, options)}`).then(
    toEpisodeListPage
  );
}

export async function openDataset(uri: string, name?: string): Promise<DatasetSummary> {
  const dataset = await request<DatasetRecordResponse>("/datasets/open", {
    method: "POST",
    body: JSON.stringify({ uri, name: name || undefined })
  });
  return fetchDatasetSummary(dataset.dataset_id);
}

export function episodeVideoUrl(datasetId: string, episodeIndex: number, camera: string): string {
  const query = new URLSearchParams({ dataset_id: datasetId });
  return `${API_BASE_URL}/episodes/${episodeIndex}/video/${encodeURIComponent(camera)}?${query}`;
}

export function episodePreviewUrl(
  datasetId: string,
  episodeIndex: number,
  camera: string,
  frameIndex = 0
): string {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    frame_index: String(frameIndex)
  });
  return `${API_BASE_URL}/episodes/${episodeIndex}/preview/${encodeURIComponent(camera)}?${query}`;
}

export async function fetchStateActionSummary(
  datasetId: string,
  episodeIndex: number,
): Promise<StateActionSummary> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  const row = await request<StateActionSummaryResponse>(
    `/episodes/${episodeIndex}/state-action?${query}`
  );
  return toStateActionSummary(row);
}

export async function fetchEpisodeTimeseries(
  datasetId: string,
  episodeIndex: number,
): Promise<EpisodeTimeseries> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  const row = await request<EpisodeTimeseriesResponse>(
    `/episodes/${episodeIndex}/timeseries?${query}`
  );
  return toEpisodeTimeseries(row);
}

export async function fetchFrameRecord(
  datasetId: string,
  episodeIndex: number,
  frameIndex: number,
): Promise<FrameRecord | null> {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex),
    start_frame: String(frameIndex),
    end_frame: String(frameIndex),
    limit: "1"
  });
  const row = await request<FrameListResponse>(`/frames?${query}`);
  const frame = row.items[0] ?? null;
  return frame ? toFrameRecord(frame) : null;
}

export async function fetchFrameWindow(
  datasetId: string,
  episodeIndex: number,
  startFrame: number,
  endFrame: number,
  limit = 32,
): Promise<FrameRecord[]> {
  const page = await fetchFrameWindowPage(datasetId, episodeIndex, startFrame, endFrame, limit);
  return page.items;
}

export async function fetchFrameWindowPage(
  datasetId: string,
  episodeIndex: number,
  startFrame: number,
  endFrame: number,
  limit = 32,
): Promise<FrameListPage> {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex),
    start_frame: String(startFrame),
    end_frame: String(endFrame),
    limit: String(limit)
  });
  const row = await request<FrameListResponse>(`/frames?${query}`);
  return toFrameListPage(row);
}

export async function updateFrameRecord(
  datasetId: string,
  episodeIndex: number,
  frameIndex: number,
  payload: FrameUpdate,
): Promise<FrameRecord> {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex)
  });
  const body: Record<string, boolean | string | null> = {};
  if (payload.isBadFrame !== undefined) {
    body.is_bad_frame = payload.isBadFrame;
  }
  if (payload.labelType !== undefined) {
    body.label_type = payload.labelType;
  }
  if (payload.labelValue !== undefined) {
    body.label_value = payload.labelValue;
  }
  if (payload.labelEnabled !== undefined) {
    body.label_enabled = payload.labelEnabled;
  }
  const row = await request<FrameRecordResponse>(`/frames/${frameIndex}?${query}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return toFrameRecord(row);
}

export async function updateEpisodeLabels(
  datasetId: string,
  episodeIndex: number,
  payload: EpisodeLabelUpdate,
): Promise<Episode> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  const body: Record<string, boolean | number | string | null> = {};
  if (payload.caption !== undefined) {
    body.caption = payload.caption;
  }
  if (payload.successLabel !== undefined) {
    body.success_label = payload.successLabel;
  }
  if (payload.failureReason !== undefined) {
    body.failure_reason = payload.failureReason;
  }
  if (payload.qualityScore !== undefined) {
    body.quality_score = payload.qualityScore;
  }
  if (payload.split !== undefined) {
    body.split = payload.split;
  }
  if (payload.reviewStatus !== undefined) {
    body.review_status = payload.reviewStatus;
  }
  if (payload.languageInstruction !== undefined) {
    body.language_instruction = payload.languageInstruction;
  }
  const row = await request<EpisodeResponse>(
    `/episodes/${episodeIndex}/labels?${query}`,
    {
      method: "PATCH",
      body: JSON.stringify(body)
    }
  );
  return toEpisode(row);
}

export async function fetchEpisodeLabelHistory(
  datasetId: string,
  episodeIndex: number,
): Promise<EpisodeLabelHistoryRecord[]> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  const rows = await request<EpisodeLabelHistoryResponse[]>(
    `/episodes/${episodeIndex}/labels/history?${query}`
  );
  return rows.map(toEpisodeLabelHistoryRecord);
}

export async function fetchAnnotations(
  datasetId: string,
  episodeIndex?: number,
): Promise<SegmentAnnotation[]> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  if (episodeIndex !== undefined) {
    query.set("episode_index", String(episodeIndex));
  }
  const rows = await request<AnnotationResponse[]>(`/annotations?${query}`);
  return rows.map(toSegmentAnnotation);
}

export async function fetchAnnotationHistory(
  datasetId: string,
  episodeIndex: number,
): Promise<AnnotationHistoryRecord[]> {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex)
  });
  const rows = await request<AnnotationHistoryResponse[]>(`/annotations/history?${query}`);
  return rows.map(toAnnotationHistoryRecord);
}

export async function createSegmentAnnotation(
  payload: SegmentAnnotationCreate,
): Promise<SegmentAnnotation> {
  const body: Record<string, unknown> = {
    dataset_id: payload.datasetId,
    episode_index: payload.episodeIndex,
    start_frame: payload.startFrame,
    end_frame: payload.endFrame,
    label_type: payload.labelType,
    label_value: payload.labelValue,
    source: payload.source ?? "human",
    confidence: payload.confidence ?? 1,
    review_status: payload.reviewStatus ?? "accepted"
  };
  if (payload.metadata !== undefined) {
    body.metadata = payload.metadata;
  }
  const row = await request<AnnotationResponse>("/annotations", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return toSegmentAnnotation(row);
}

export async function updateAnnotationReviewStatus(
  annotationId: string,
  reviewStatus: ReviewStatus,
  expectedRevision?: number,
): Promise<SegmentAnnotation> {
  const body: Record<string, number | string> = { review_status: reviewStatus };
  if (expectedRevision !== undefined) {
    body.expected_revision = expectedRevision;
  }
  const row = await request<AnnotationResponse>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return toSegmentAnnotation(row);
}

export async function assignAnnotation(
  annotationId: string,
  assignedTo: string | null,
  expectedRevision?: number,
): Promise<SegmentAnnotation> {
  const body: Record<string, number | string | null> = { assigned_to: assignedTo };
  if (expectedRevision !== undefined) {
    body.expected_revision = expectedRevision;
  }
  const row = await request<AnnotationResponse>(`/annotations/${annotationId}/assignment`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return toSegmentAnnotation(row);
}

export async function updateSegmentAnnotation(
  annotationId: string,
  payload: SegmentAnnotationUpdate,
): Promise<SegmentAnnotation> {
  const body: Record<string, unknown> = {};
  if (payload.startFrame !== undefined) {
    body.start_frame = payload.startFrame;
  }
  if (payload.endFrame !== undefined) {
    body.end_frame = payload.endFrame;
  }
  if (payload.labelType !== undefined) {
    body.label_type = payload.labelType;
  }
  if (payload.labelValue !== undefined) {
    body.label_value = payload.labelValue;
  }
  if (payload.reviewStatus !== undefined) {
    body.review_status = payload.reviewStatus;
  }
  if (payload.assignedTo !== undefined) {
    body.assigned_to = payload.assignedTo;
  }
  if (payload.expectedRevision !== undefined) {
    body.expected_revision = payload.expectedRevision;
  }
  if (payload.metadata !== undefined) {
    body.metadata = payload.metadata;
  }
  const row = await request<AnnotationResponse>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return toSegmentAnnotation(row);
}

export async function deleteAnnotation(annotationId: string, expectedRevision?: number): Promise<void> {
  const query = new URLSearchParams();
  if (expectedRevision !== undefined) {
    query.set("expected_revision", String(expectedRevision));
  }
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  await request<{ status: string }>(`/annotations/${annotationId}${suffix}`, {
    method: "DELETE"
  });
}

export async function createRerunSession(
  datasetId: string,
  episodeIndex: number,
  publishUri?: string,
): Promise<RerunSession> {
  const body: Record<string, object | string | number | null> = {
    dataset_id: datasetId,
    episode_index: episodeIndex,
    mode: "rrd_cache"
  };
  if (publishUri !== undefined) {
    body.publish_uri = publishUri || null;
  }
  const row = await request<RerunSessionResponse>("/rerun/session", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return toRerunSession(row);
}

export async function fetchRerunSession(sessionId: string): Promise<RerunSession> {
  const row = await request<RerunSessionResponse>(`/rerun/session/${sessionId}`);
  return toRerunSession(row);
}

export async function createRerunSessionJob(
  datasetId: string,
  episodeIndex: number,
  publishUri?: string,
): Promise<JobRecord> {
  const body: Record<string, object | string | number | null> = {
    dataset_id: datasetId,
    episode_index: episodeIndex,
    mode: "rrd_cache"
  };
  if (publishUri !== undefined) {
    body.publish_uri = publishUri || null;
  }
  const row = await request<JobRecordResponse>("/jobs/rerun-session", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return toJobRecord(row);
}

export async function createVlmLabelJob(
  datasetId: string,
  episodeIndices: number[],
): Promise<JobRecord> {
  const row = await request<JobRecordResponse>("/jobs/vlm-label", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      episode_indices: episodeIndices,
      model: VLM_MODEL,
      prompt_template: VLM_PROMPT_TEMPLATE,
      min_keyframes: VLM_MIN_KEYFRAMES,
      max_keyframes: VLM_MAX_KEYFRAMES
    })
  });
  return toJobRecord(row);
}

export async function fetchVlmResponses(jobId: string): Promise<VlmResponseRecord[]> {
  const rows = await request<VlmResponseRecordResponse[]>(`/jobs/${jobId}/vlm-responses`);
  return rows.map(toVlmResponseRecord);
}

export async function createVisualEmbeddingJob(
  datasetId: string,
  episodeIndices: number[],
  model = "deterministic-visual",
): Promise<JobRecord> {
  const row = await request<JobRecordResponse>("/jobs/visual-embeddings", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      episode_indices: episodeIndices,
      model
    })
  });
  return toJobRecord(row);
}

export async function createExportJob(
  datasetId: string,
  episodeIndices: number[],
  format: ExportFormat = "lance",
  splits: string[] = [],
  publishUri?: string,
  options?: SkillExportOptions,
): Promise<JobRecord> {
  const body: Record<string, unknown> = {
    dataset_id: datasetId,
    episode_indices: episodeIndices,
    splits,
    format,
    version_description: `web skill clip ${format} export`,
    clip_label_type: options?.clipLabelType ?? "skill",
    accepted_clips_only: options?.acceptedClipsOnly ?? true,
    materialize_skill_clips: options?.materializeSkillClips ?? format === "lance",
    jitter_offsets: options?.jitterOffsets ?? [0],
    copies_per_clip: options?.copiesPerClip ?? 1
  };
  if (publishUri !== undefined) {
    body.publish_uri = publishUri || null;
  }
  const row = await request<JobRecordResponse>("/jobs/export", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return toJobRecord(row);
}

export function jobEventsUrl(jobId: string): string {
  return `${API_BASE_URL}/jobs/${jobId}/events`;
}

export async function streamJobEvents(
  jobId: string,
  onEvent: (event: JobProgressEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(jobEventsUrl(jobId), {
    headers: {
      Accept: "text/event-stream",
      ...(API_KEY ? { "X-Robot-Data-Studio-API-Key": API_KEY } : {}),
      ...(REVIEW_USER ? { "X-Robot-Data-Studio-User": REVIEW_USER } : {})
    },
    signal
  });
  if (!response.ok) {
    throw new Error(`Job event stream failed: ${response.status} ${response.statusText}`);
  }
  if (!response.body) {
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = splitSseEvents(buffer);
    buffer = events.remainder;
    for (const rawEvent of events.items) {
      const event = parseJobSseEvent(rawEvent);
      if (event) {
        onEvent(event);
      }
    }
  }
}

export async function fetchCurrentUser(): Promise<UserIdentity> {
  const row = await request<UserIdentityResponse>("/users/me");
  return { userId: row.user_id };
}

export async function createExport(
  datasetId: string,
  episodeIndices: number[],
  format: ExportFormat = "lance",
  splits: string[] = [],
  publishUri?: string,
): Promise<ExportRecord> {
  const body: Record<string, string | string[] | number[] | ExportFormat | null> = {
    dataset_id: datasetId,
    episode_indices: episodeIndices,
    splits,
    format,
    version_description: `web selected episode ${format} export`
  };
  if (publishUri !== undefined) {
    body.publish_uri = publishUri || null;
  }
  const row = await request<ExportRecordResponse>("/exports", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return toExportRecord(row);
}

export async function fetchExport(exportId: string): Promise<ExportRecord> {
  const row = await request<ExportRecordResponse>(`/exports/${exportId}`);
  return toExportRecord(row);
}

export async function semanticSearch(
  datasetId: string,
  text: string,
  filterQuery?: string,
): Promise<SearchResult[]> {
  const body: Record<string, number | string | string[]> = {
    dataset_id: datasetId,
    text,
    limit: 10
  };
  if (filterQuery?.trim()) {
    body.filter_query = filterQuery.trim();
  }
  const rows = await request<SearchResultResponse[]>("/search/semantic", {
    method: "POST",
    body: JSON.stringify(body)
  });
  return rows.map(toSearchResult);
}

export async function fullTextSearch(datasetId: string, text: string): Promise<SearchResult[]> {
  const rows = await request<SearchResultResponse[]>("/search/full-text", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      text,
      limit: 50
    })
  });
  return rows.map(toSearchResult);
}

export async function filterSearch(datasetId: string, query: string): Promise<SearchResult[]> {
  const rows = await request<SearchResultResponse[]>("/search/filter", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      query,
      limit: 100
    })
  });
  return rows.map(toSearchResult);
}

export async function fetchFilterPresets(datasetId: string): Promise<FilterPreset[]> {
  const query = new URLSearchParams({ dataset_id: datasetId });
  const rows = await request<FilterPresetResponse[]>(`/search/filter-presets?${query}`);
  return rows.map(toFilterPreset);
}

export async function createFilterPreset(
  datasetId: string,
  name: string,
  query: string,
): Promise<FilterPreset> {
  const row = await request<FilterPresetResponse>("/search/filter-presets", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      name,
      query
    })
  });
  return toFilterPreset(row);
}

export async function deleteFilterPreset(presetId: string): Promise<void> {
  await request<{ status: string }>(`/search/filter-presets/${presetId}`, {
    method: "DELETE"
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-Robot-Data-Studio-API-Key": API_KEY } : {}),
      ...(REVIEW_USER ? { "X-Robot-Data-Studio-User": REVIEW_USER } : {}),
      ...init?.headers
    }
  });
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    const message = detail || `API request failed: ${response.status} ${response.statusText}`;
    if (response.status === 409) {
      throw new ApiConflictError(message);
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
  } catch {
    return null;
  }
  return null;
}

function splitSseEvents(buffer: string): { items: string[]; remainder: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const remainder = parts.pop() ?? "";
  return {
    items: parts.filter((part) => part.trim().length > 0),
    remainder
  };
}

function parseJobSseEvent(rawEvent: string): JobProgressEvent | null {
  const lines = rawEvent.split("\n");
  const eventType = lines
    .find((line) => line.startsWith("event:"))
    ?.slice("event:".length)
    .trim();
  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trim());
  if (eventType !== "job" || dataLines.length === 0) {
    return null;
  }
  const payload = JSON.parse(dataLines.join("\n")) as JobProgressEventResponse;
  return {
    jobId: payload.job_id,
    kind: payload.kind,
    status: payload.status,
    progress: payload.progress,
    message: payload.message,
    queueJobId: payload.queue_job_id,
    rawResponseIds: payload.raw_response_ids ?? [],
    rawResponseUri: payload.raw_response_uri ?? null,
    createdExportId: payload.created_export_id,
    exportFormat: payload.export_format,
    exportUri: payload.export_uri,
    createdRerunSessionId: payload.created_rerun_session_id,
    rerunRrdUrl: payload.rerun_rrd_url,
    rerunRrdPath: payload.rerun_rrd_path,
    rerunPublishedUri: payload.rerun_published_uri,
    rerunViewerUrl: payload.rerun_viewer_url
  };
}

function toVlmResponseRecord(raw: VlmResponseRecordResponse): VlmResponseRecord {
  return {
    responseId: raw.response_id,
    datasetId: raw.dataset_id,
    jobId: raw.job_id,
    episodeIndex: raw.episode_index,
    provider: raw.provider,
    createdAt: raw.created_at,
    rawResponse: raw.raw_response
  };
}

function toDatasetSummary(raw: DatasetSummaryResponse): DatasetSummary {
  return {
    datasetId: raw.dataset_id,
    name: raw.name,
    uri: raw.uri,
    status: raw.status,
    episodeCount: raw.episode_count,
    frameCount: raw.frame_count,
    fps: raw.fps ?? 0,
    cameraNames: raw.camera_names,
    cameraInfo: raw.camera_info ?? null,
    reviewedCount: raw.reviewed_count,
    acceptedCount: raw.accepted_count,
    rejectedCount: raw.rejected_count,
    message: raw.message
  };
}

function toDatasetHealth(raw: DatasetHealthResponse): DatasetHealth {
  return {
    datasetId: raw.dataset_id,
    ok: raw.ok,
    status: raw.status,
    storageModel: raw.storage_model,
    level: raw.level ?? "shallow",
    episodeCount: raw.episode_count,
    frameCount: raw.frame_count,
    cameraCount: raw.camera_count,
    tables: raw.tables.map(toDatasetTableHealth),
    warnings: raw.warnings,
    errors: raw.errors
  };
}

function toDatasetTableHealth(raw: DatasetTableHealthResponse): DatasetTableHealth {
  return {
    table: raw.table,
    present: raw.present,
    rowCount: raw.row_count,
    columns: raw.columns,
    missingRequiredColumns: raw.missing_required_columns,
    warnings: raw.warnings
  };
}

function toEpisode(raw: EpisodeResponse): Episode {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    taskIndex: raw.task_index ?? 0,
    length: raw.length ?? 0,
    successLabel: raw.success_label,
    qualityScore: raw.quality_score,
    reviewStatus: raw.review_status,
    caption: raw.caption ?? "",
    failureReason: raw.failure_reason ?? "",
    hasVlmLabel: raw.has_vlm_label,
    hasHumanLabel: raw.has_human_label,
    split: raw.split,
    fps: raw.fps ?? 0,
    cameraNames: raw.camera_names ?? [],
    languageInstruction: raw.language_instruction ?? null
  };
}

function toEpisodeListPage(raw: EpisodeListPageResponse): EpisodeListPage {
  return {
    datasetId: raw.dataset_id,
    items: raw.items.map(toEpisode),
    total: raw.total,
    limit: raw.limit,
    offset: raw.offset,
    nextOffset: raw.next_offset,
    previousOffset: raw.previous_offset,
    sortBy: raw.sort_by,
    sortOrder: raw.sort_order,
    filterQuery: raw.filter_query
  };
}

function toStateActionSummary(raw: StateActionSummaryResponse): StateActionSummary {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    frameCount: raw.frame_count,
    stateDim: raw.state_dim,
    actionDim: raw.action_dim,
    stateNormMin: raw.state_norm_min,
    stateNormMax: raw.state_norm_max,
    actionNormMin: raw.action_norm_min,
    actionNormMax: raw.action_norm_max
  };
}

function toEpisodeTimeseries(raw: EpisodeTimeseriesResponse): EpisodeTimeseries {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    frameCount: raw.frame_count,
    fps: raw.fps,
    sampleCount: raw.sample_count,
    sampleIndices: raw.sample_indices,
    timestamps: raw.timestamps,
    stateNorms: raw.state_norms,
    actionNorms: raw.action_norms,
    stateValues: raw.state_values ?? [],
    actionValues: raw.action_values ?? [],
    stateDim: raw.state_dim,
    actionDim: raw.action_dim
  };
}

function toFrameRecord(raw: FrameRecordResponse): FrameRecord {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    frameIndex: raw.frame_index,
    timestamp: raw.timestamp,
    taskIndex: raw.task_index,
    observationState: raw.observation_state,
    action: raw.action,
    stateNorm: raw.state_norm,
    actionNorm: raw.action_norm,
    isBadFrame: raw.is_bad_frame,
    labels: raw.labels.map((label) => ({
      annotationId: label.annotation_id,
      labelType: label.label_type,
      labelValue: label.label_value,
      source: label.source,
      confidence: label.confidence,
      reviewStatus: label.review_status
    }))
  };
}

function toFrameListPage(raw: FrameListResponse): FrameListPage {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    frameCount: raw.frame_count,
    startFrame: raw.start_frame,
    endFrame: raw.end_frame,
    limit: raw.limit,
    returnedCount: raw.returned_count,
    items: raw.items.map(toFrameRecord)
  };
}

function toSegmentAnnotation(raw: AnnotationResponse): SegmentAnnotation {
  return {
    id: raw.annotation_id,
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    startFrame: raw.start_frame,
    endFrame: raw.end_frame,
    labelType: raw.label_type,
    labelValue: raw.label_value,
    source: raw.source,
    confidence: raw.confidence,
    reviewStatus: raw.review_status,
    metadata: toSegmentMetadata(raw.metadata),
    createdBy: raw.created_by,
    updatedBy: raw.updated_by ?? raw.created_by,
    assignedTo: raw.assigned_to,
    revision: raw.revision ?? 1,
    deletedAt: raw.deleted_at ?? null,
    lockOwner: raw.lock_owner ?? null,
    lockExpiresAt: raw.lock_expires_at ?? null
  };
}

function toSegmentMetadata(raw: Record<string, unknown> | null | undefined): SegmentAnnotation["metadata"] {
  if (raw === null || raw === undefined || Array.isArray(raw)) {
    return {};
  }
  return {
    skillId: typeof raw.skillId === "number" ? raw.skillId : typeof raw.skill_id === "number" ? raw.skill_id : undefined,
    qualityScore:
      typeof raw.qualityScore === "number"
        ? raw.qualityScore
        : typeof raw.quality_score === "number"
          ? raw.quality_score
          : null,
    successLabel:
      typeof raw.successLabel === "boolean"
        ? raw.successLabel
        : typeof raw.success_label === "boolean"
          ? raw.success_label
          : null,
    failureReason:
      typeof raw.failureReason === "string"
        ? raw.failureReason
        : typeof raw.failure_reason === "string"
          ? raw.failure_reason
          : null,
    split: raw.split === "train" || raw.split === "val" || raw.split === "test" ? raw.split : null,
    targetObject:
      typeof raw.targetObject === "string"
        ? raw.targetObject
        : typeof raw.target_object === "string"
          ? raw.target_object
          : null,
    handMode: raw.handMode === "left" || raw.handMode === "right" || raw.handMode === "both"
      ? raw.handMode
      : raw.hand_mode === "left" || raw.hand_mode === "right" || raw.hand_mode === "both"
        ? raw.hand_mode
        : null,
    notes: typeof raw.notes === "string" ? raw.notes : null
  };
}

function toAnnotationHistoryRecord(raw: AnnotationHistoryResponse): AnnotationHistoryRecord {
  return {
    eventId: raw.event_id,
    datasetId: raw.dataset_id,
    annotationId: raw.annotation_id,
    episodeIndex: raw.episode_index,
    action: raw.action,
    actor: raw.actor,
    before: raw.before,
    after: raw.after,
    createdAt: raw.created_at
  };
}

function toEpisodeLabelHistoryRecord(
  raw: EpisodeLabelHistoryResponse
): EpisodeLabelHistoryRecord {
  return {
    eventId: raw.event_id,
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    action: raw.action,
    actor: raw.actor,
    before: raw.before,
    after: raw.after,
    createdAt: raw.created_at
  };
}

function toRerunSession(raw: RerunSessionResponse): RerunSession {
  return {
    sessionId: raw.session_id,
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    mode: raw.mode,
    status: raw.status,
    cacheKey: raw.cache_key,
    cacheHit: raw.cache_hit,
    cameraCount: raw.camera_count,
    viewerUrl: raw.viewer_url,
    rrdUrl: raw.rrd_url ? `${API_ROOT_URL}${raw.rrd_url}` : null,
    publishedUri: raw.published_uri,
    publishSizeBytes: raw.publish_size_bytes,
    message: raw.message
  };
}

function toJobRecord(raw: JobRecordResponse): JobRecord {
  return {
    jobId: raw.job_id,
    kind: raw.kind,
    status: raw.status,
    datasetId: raw.dataset_id,
    episodeIndices: raw.episode_indices,
    progress: raw.progress,
    message: raw.message,
    createdAnnotationIds: raw.created_annotation_ids,
    model: raw.model,
    promptTemplate: raw.prompt_template,
    promptVersion: raw.prompt_version,
    provider: raw.provider,
    rawResponseIds: raw.raw_response_ids ?? [],
    rawResponseUri: raw.raw_response_uri ?? null,
    createdEmbeddingIds: raw.created_embedding_ids,
    artifactCount: raw.artifact_count,
    createdExportId: raw.created_export_id,
    exportFormat: raw.export_format,
    exportUri: raw.export_uri,
    createdRerunSessionId: raw.created_rerun_session_id,
    rerunRrdUrl: raw.rerun_rrd_url,
    rerunRrdPath: raw.rerun_rrd_path,
    rerunPublishedUri: raw.rerun_published_uri,
    rerunViewerUrl: raw.rerun_viewer_url,
    queueJobId: raw.queue_job_id
  };
}

function toExportRecord(raw: ExportRecordResponse): ExportRecord {
  return {
    exportId: raw.export_id,
    datasetId: raw.dataset_id,
    episodeIndices: raw.episode_indices,
    format: raw.format,
    status: raw.status,
    outputUri: raw.output_uri,
    message: raw.message,
    artifacts: raw.artifacts ?? null
  };
}

function toSearchResult(raw: SearchResultResponse): SearchResult {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    frameIndex: raw.frame_index,
    score: raw.score,
    matchType: raw.match_type,
    label: raw.label,
    modality: raw.modality ?? null,
    sourceModel: raw.source_model ?? null,
    camera: raw.camera ?? null,
    sourceUri: raw.source_uri ?? null
  };
}

function toFilterPreset(raw: FilterPresetResponse): FilterPreset {
  return {
    presetId: raw.preset_id,
    datasetId: raw.dataset_id,
    name: raw.name,
    query: raw.query,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at
  };
}
