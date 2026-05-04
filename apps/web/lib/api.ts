import type { DatasetSummary, Episode } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

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
  quality_score: number | null;
  review_status: Episode["reviewStatus"];
  caption: string | null;
  has_vlm_label: boolean;
  has_human_label: boolean;
  split: string | null;
  fps?: number | null;
  camera_names?: string[];
};

export async function fetchDatasetSummaries(): Promise<DatasetSummary[]> {
  const datasets = await request<DatasetRecordResponse[]>("/datasets");
  return Promise.all(datasets.map((dataset) => fetchDatasetSummary(dataset.dataset_id)));
}

export async function fetchDatasetSummary(datasetId: string): Promise<DatasetSummary> {
  return request<DatasetSummaryResponse>(`/datasets/${datasetId}/summary`).then(toDatasetSummary);
}

export async function fetchEpisodes(datasetId: string): Promise<Episode[]> {
  const episodes = await request<EpisodeResponse[]>(
    `/episodes?dataset_id=${encodeURIComponent(datasetId)}&limit=200`
  );
  return episodes.map(toEpisode);
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
    hasVlmLabel: raw.has_vlm_label,
    hasHumanLabel: raw.has_human_label,
    split: raw.split ?? "",
    fps: raw.fps ?? 0,
    cameraNames: raw.camera_names ?? []
  };
}
