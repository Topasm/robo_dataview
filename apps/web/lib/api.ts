import type {
  DatasetSummary,
  Episode,
  EpisodeListPage,
  EpisodeTimeseries,
  ExportRecord,
  FilterPreset,
  FrameRecord,
  JobRecord,
  RerunSession,
  ReviewStatus,
  SearchResult,
  SegmentAnnotation,
  StateActionSummary
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const API_ROOT_URL = API_BASE_URL.endsWith("/api")
  ? API_BASE_URL.slice(0, -"/api".length)
  : API_BASE_URL;
const VLM_MODEL = process.env.NEXT_PUBLIC_VLM_MODEL ?? "heuristic-vlm-fallback";
const VLM_PROMPT_TEMPLATE = process.env.NEXT_PUBLIC_VLM_PROMPT_TEMPLATE ?? "episode_autolabel_v1";

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
  reviewed_count: number;
  accepted_count: number;
  rejected_count: number;
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
};

export type SegmentAnnotationUpdate = {
  startFrame?: number;
  endFrame?: number;
  labelType?: string;
  labelValue?: string;
  reviewStatus?: ReviewStatus;
};

export type EpisodeLabelUpdate = {
  caption?: string | null;
  successLabel?: boolean | null;
  failureReason?: string | null;
  qualityScore?: number | null;
  split?: string | null;
  reviewStatus?: ReviewStatus | null;
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
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex),
    start_frame: String(startFrame),
    end_frame: String(endFrame),
    limit: String(limit)
  });
  const row = await request<FrameListResponse>(`/frames?${query}`);
  return row.items.map(toFrameRecord);
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
  const row = await request<EpisodeResponse>(
    `/episodes/${episodeIndex}/labels?${query}`,
    {
      method: "PATCH",
      body: JSON.stringify(body)
    }
  );
  return toEpisode(row);
}

export async function fetchAnnotations(
  datasetId: string,
  episodeIndex: number,
): Promise<SegmentAnnotation[]> {
  const query = new URLSearchParams({
    dataset_id: datasetId,
    episode_index: String(episodeIndex)
  });
  const rows = await request<AnnotationResponse[]>(`/annotations?${query}`);
  return rows.map(toSegmentAnnotation);
}

export async function createSegmentAnnotation(
  payload: SegmentAnnotationCreate,
): Promise<SegmentAnnotation> {
  const row = await request<AnnotationResponse>("/annotations", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: payload.datasetId,
      episode_index: payload.episodeIndex,
      start_frame: payload.startFrame,
      end_frame: payload.endFrame,
      label_type: payload.labelType,
      label_value: payload.labelValue,
      source: payload.source ?? "human",
      confidence: payload.confidence ?? 1,
      review_status: payload.reviewStatus ?? "accepted"
    })
  });
  return toSegmentAnnotation(row);
}

export async function updateAnnotationReviewStatus(
  annotationId: string,
  reviewStatus: ReviewStatus,
): Promise<SegmentAnnotation> {
  const row = await request<AnnotationResponse>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify({ review_status: reviewStatus })
  });
  return toSegmentAnnotation(row);
}

export async function updateSegmentAnnotation(
  annotationId: string,
  payload: SegmentAnnotationUpdate,
): Promise<SegmentAnnotation> {
  const body: Record<string, number | string> = {};
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
  const row = await request<AnnotationResponse>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return toSegmentAnnotation(row);
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
  await request<{ status: string }>(`/annotations/${annotationId}`, {
    method: "DELETE"
  });
}

export async function createRerunSession(
  datasetId: string,
  episodeIndex: number,
): Promise<RerunSession> {
  const row = await request<RerunSessionResponse>("/rerun/session", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      episode_index: episodeIndex,
      mode: "rrd_cache"
    })
  });
  return toRerunSession(row);
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
      prompt_template: VLM_PROMPT_TEMPLATE
    })
  });
  return toJobRecord(row);
}

export async function createExport(
  datasetId: string,
  episodeIndices: number[],
  format: "lerobot" | "lance" | "jsonl" | "vla" = "lerobot",
  splits: string[] = [],
): Promise<ExportRecord> {
  const row = await request<ExportRecordResponse>("/exports", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      episode_indices: episodeIndices,
      splits,
      format,
      version_description: `web selected episode ${format} export`
    })
  });
  return toExportRecord(row);
}

export async function semanticSearch(
  datasetId: string,
  text: string,
  filterQuery?: string,
): Promise<SearchResult[]> {
  const body: Record<string, number | string> = {
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
      ...init?.headers
    }
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
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
    reviewedCount: raw.reviewed_count,
    acceptedCount: raw.accepted_count,
    rejectedCount: raw.rejected_count,
    message: raw.message
  };
}

function toEpisode(raw: EpisodeResponse): Episode {
  return {
    datasetId: raw.dataset_id,
    episodeIndex: raw.episode_index,
    taskIndex: raw.task_index ?? 0,
    length: raw.length ?? 0,
    successLabel: raw.success_label,
    qualityScore: raw.quality_score ?? 0,
    reviewStatus: raw.review_status,
    caption: raw.caption ?? "",
    failureReason: raw.failure_reason ?? "",
    hasVlmLabel: raw.has_vlm_label,
    hasHumanLabel: raw.has_human_label,
    split: raw.split ?? "",
    fps: raw.fps ?? 0,
    cameraNames: raw.camera_names ?? []
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
    reviewStatus: raw.review_status
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
    rawResponseIds: raw.raw_response_ids,
    rawResponseUri: raw.raw_response_uri
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
    label: raw.label
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
