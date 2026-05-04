import type { DatasetSummary, Episode, SegmentAnnotation } from "./types";

export const datasetSummary: DatasetSummary = {
  datasetId: "sample-xvla-soft-fold",
  name: "sample-xvla-soft-fold",
  uri: "sample://xvla-soft-fold",
  status: "sample",
  episodeCount: 3,
  frameCount: 576,
  fps: 20,
  cameraNames: ["cam_high", "cam_left_wrist", "cam_right_wrist"],
  reviewedCount: 2,
  acceptedCount: 2,
  rejectedCount: 0
};

export const episodes: Episode[] = [
  {
    datasetId: datasetSummary.datasetId,
    episodeIndex: 0,
    taskIndex: 3,
    length: 180,
    successLabel: true,
    qualityScore: 0.72,
    reviewStatus: "accepted",
    caption: "Soft cloth folding trajectory",
    failureReason: "",
    hasVlmLabel: false,
    hasHumanLabel: false,
    split: "train",
    fps: 20,
    cameraNames: datasetSummary.cameraNames
  },
  {
    datasetId: datasetSummary.datasetId,
    episodeIndex: 1,
    taskIndex: 3,
    length: 192,
    successLabel: false,
    qualityScore: 0.77,
    reviewStatus: "pending",
    caption: "Failed fold with cloth slip",
    failureReason: "cloth slip",
    hasVlmLabel: true,
    hasHumanLabel: false,
    split: "train",
    fps: 20,
    cameraNames: datasetSummary.cameraNames
  },
  {
    datasetId: datasetSummary.datasetId,
    episodeIndex: 2,
    taskIndex: 3,
    length: 204,
    successLabel: true,
    qualityScore: 0.82,
    reviewStatus: "accepted",
    caption: "Clean edge grasp and fold",
    failureReason: "",
    hasVlmLabel: true,
    hasHumanLabel: true,
    split: "val",
    fps: 20,
    cameraNames: datasetSummary.cameraNames
  }
];

export const annotations: SegmentAnnotation[] = [
  {
    id: "seg-approach",
    datasetId: datasetSummary.datasetId,
    episodeIndex: 0,
    startFrame: 0,
    endFrame: 38,
    labelType: "phase",
    labelValue: "approach",
    source: "human",
    confidence: 1,
    reviewStatus: "accepted"
  },
  {
    id: "seg-grasp",
    datasetId: datasetSummary.datasetId,
    episodeIndex: 0,
    startFrame: 39,
    endFrame: 88,
    labelType: "phase",
    labelValue: "cloth_edge_grasp",
    source: "vlm",
    confidence: 0.82,
    reviewStatus: "pending"
  },
  {
    id: "seg-fold",
    datasetId: datasetSummary.datasetId,
    episodeIndex: 0,
    startFrame: 89,
    endFrame: 156,
    labelType: "phase",
    labelValue: "fold",
    source: "human",
    confidence: 1,
    reviewStatus: "accepted"
  },
  {
    id: "seg-release",
    datasetId: datasetSummary.datasetId,
    episodeIndex: 0,
    startFrame: 157,
    endFrame: 180,
    labelType: "phase",
    labelValue: "release",
    source: "heuristic",
    confidence: 0.64,
    reviewStatus: "pending"
  }
];
