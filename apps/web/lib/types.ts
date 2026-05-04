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
  hasVlmLabel: boolean;
  hasHumanLabel: boolean;
  split: string;
  fps: number;
  cameraNames: string[];
};

export type SegmentAnnotation = {
  id: string;
  startFrame: number;
  endFrame: number;
  labelType: string;
  labelValue: string;
  source: "human" | "vlm" | "heuristic" | "import";
  confidence: number;
  reviewStatus: ReviewStatus;
};
