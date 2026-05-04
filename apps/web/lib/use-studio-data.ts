"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createExport,
  createFilterPreset,
  createRerunSession,
  createSegmentAnnotation,
  createVlmLabelJob,
  deleteAnnotation,
  deleteFilterPreset,
  fetchAnnotations,
  fetchDatasetSummaries,
  fetchEpisodes,
  fetchFilterPresets,
  fetchFrameRecord,
  filterSearch,
  fullTextSearch,
  openDataset,
  semanticSearch,
  updateEpisodeLabels,
  updateSegmentAnnotation,
  updateAnnotationReviewStatus,
  updateFrameRecord
} from "@/lib/api";
import { annotations, datasetSummary, episodes } from "@/lib/sample-data";
import type {
  DatasetSummary,
  Episode,
  ExportRecord,
  FilterPreset,
  FrameRecord,
  JobRecord,
  RerunSession,
  ReviewStatus,
  SearchResult,
  SegmentAnnotation
} from "@/lib/types";

type SegmentDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
};

type EpisodeLabelDraft = {
  caption: string;
  successLabel: boolean | null;
  failureReason: string;
  qualityScore: number;
  split: string;
  reviewStatus: ReviewStatus;
};

export function useStudioData() {
  const [summaries, setSummaries] = useState<DatasetSummary[]>([datasetSummary]);
  const [episodeRows, setEpisodeRows] = useState<Episode[]>(episodes);
  const [selectedDatasetId, setSelectedDatasetId] = useState(datasetSummary.datasetId);
  const [selectedEpisodeIndex, setSelectedEpisodeIndex] = useState(episodes[0].episodeIndex);
  const [annotationRows, setAnnotationRows] = useState<SegmentAnnotation[]>(annotations);
  const [rerunSession, setRerunSession] = useState<RerunSession | null>(null);
  const [vlmJob, setVlmJob] = useState<JobRecord | null>(null);
  const [exportRecord, setExportRecord] = useState<ExportRecord | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [filterPresets, setFilterPresets] = useState<FilterPreset[]>([]);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState(0);
  const [selectedFrameRecord, setSelectedFrameRecord] = useState<FrameRecord | null>(null);
  const [selectedFrameStatus, setSelectedFrameStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [dataStatus, setDataStatus] = useState<"loading" | "api" | "sample">("loading");

  const selectedSummary =
    summaries.find((summary) => summary.datasetId === selectedDatasetId) ??
    summaries[0] ??
    datasetSummary;

  const selectedEpisode = useMemo(
    () =>
      episodeRows.find((episode) => episode.episodeIndex === selectedEpisodeIndex) ??
      episodeRows[0] ??
      episodes[0],
    [episodeRows, selectedEpisodeIndex]
  );

  const rerunViewerUrl = process.env.NEXT_PUBLIC_RERUN_IFRAME_URL ?? null;

  useEffect(() => {
    let isMounted = true;

    async function loadInitialData() {
      try {
        const apiSummaries = await fetchDatasetSummaries();
        if (!isMounted || apiSummaries.length === 0) {
          return;
        }
        const datasetId = apiSummaries[0].datasetId;
        const apiEpisodes = await fetchEpisodes(datasetId);
        if (!isMounted) {
          return;
        }
        setSummaries(apiSummaries);
        setSelectedDatasetId(datasetId);
        setEpisodeRows(apiEpisodes.length > 0 ? apiEpisodes : []);
        setSelectedEpisodeIndex(apiEpisodes[0]?.episodeIndex ?? 0);
        resetDerivedState();
        setDataStatus("api");
      } catch {
        if (!isMounted) {
          return;
        }
        setSummaries([datasetSummary]);
        setSelectedDatasetId(datasetSummary.datasetId);
        setEpisodeRows(episodes);
        setSelectedEpisodeIndex(episodes[0].episodeIndex);
        resetDerivedState();
        setDataStatus("sample");
      }
    }

    loadInitialData();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadAnnotations() {
      try {
        const apiAnnotations = await fetchAnnotations(
          selectedEpisode.datasetId,
          selectedEpisode.episodeIndex
        );
        if (isMounted) {
          setAnnotationRows(apiAnnotations);
        }
      } catch {
        if (isMounted) {
          setAnnotationRows(
            annotations.filter(
              (annotation) =>
                annotation.datasetId === selectedEpisode.datasetId &&
                annotation.episodeIndex === selectedEpisode.episodeIndex
            )
          );
        }
      }
    }

    loadAnnotations();
    return () => {
      isMounted = false;
    };
  }, [selectedEpisode.datasetId, selectedEpisode.episodeIndex]);

  useEffect(() => {
    setSelectedFrameIndex(0);
    setSelectedFrameRecord(null);
    setSelectedFrameStatus("idle");
  }, [selectedEpisode.datasetId, selectedEpisode.episodeIndex]);

  useEffect(() => {
    if (selectedEpisode.length <= 0) {
      setSelectedFrameRecord(null);
      setSelectedFrameStatus("idle");
      return;
    }

    let isMounted = true;
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const frameIndex = Math.max(0, Math.min(maxFrame, Math.round(selectedFrameIndex)));
    setSelectedFrameStatus("loading");
    const timeoutId = window.setTimeout(() => {
      fetchFrameRecord(selectedEpisode.datasetId, selectedEpisode.episodeIndex, frameIndex)
        .then((frame) => {
          if (isMounted) {
            setSelectedFrameRecord(frame);
            setSelectedFrameStatus(frame ? "ready" : "error");
          }
        })
        .catch(() => {
          if (isMounted) {
            setSelectedFrameRecord(null);
            setSelectedFrameStatus("error");
          }
        });
    }, 120);

    return () => {
      isMounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [
    selectedEpisode.datasetId,
    selectedEpisode.episodeIndex,
    selectedEpisode.length,
    selectedFrameIndex
  ]);

  useEffect(() => {
    let isMounted = true;

    async function loadFilterPresets() {
      try {
        const presets = await fetchFilterPresets(selectedDatasetId);
        if (isMounted) {
          setFilterPresets(presets);
        }
      } catch {
        if (isMounted) {
          setFilterPresets([]);
        }
      }
    }

    loadFilterPresets();
    return () => {
      isMounted = false;
    };
  }, [selectedDatasetId]);

  function resetDerivedState() {
    setRerunSession(null);
    setVlmJob(null);
    setExportRecord(null);
    setSearchResults([]);
    setFilterPresets([]);
  }

  async function handleOpenDataset(uri: string) {
    const summary = await openDataset(uri);
    const apiEpisodes = await fetchEpisodes(summary.datasetId);
    setSummaries((current) => {
      const existing = current.filter((item) => item.datasetId !== summary.datasetId);
      return [summary, ...existing];
    });
    setSelectedDatasetId(summary.datasetId);
    setEpisodeRows(apiEpisodes);
    setSelectedEpisodeIndex(apiEpisodes[0]?.episodeIndex ?? 0);
    resetDerivedState();
    setDataStatus("api");
  }

  function handleSelectEpisode(episodeIndex: number) {
    setSelectedEpisodeIndex(episodeIndex);
    setSelectedFrameIndex(0);
    setSelectedFrameRecord(null);
    setSelectedFrameStatus("idle");
    setRerunSession(null);
    setVlmJob(null);
    setExportRecord(null);
  }

  const handleSelectFrame = useCallback((frameIndex: number) => {
    setSelectedFrameIndex(Math.max(0, Math.round(frameIndex)));
  }, []);

  async function handleCreateSegment(draft: SegmentDraft) {
    const created = await createSegmentAnnotation({
      datasetId: selectedEpisode.datasetId,
      episodeIndex: selectedEpisode.episodeIndex,
      startFrame: draft.startFrame,
      endFrame: draft.endFrame,
      labelType: draft.labelType,
      labelValue: draft.labelValue,
      source: "human",
      confidence: 1,
      reviewStatus: "accepted"
    });
    setAnnotationRows((current) => [...current, created].sort((a, b) => a.startFrame - b.startFrame));
  }

  async function handleUpdateEpisodeLabels(draft: EpisodeLabelDraft) {
    const updated = await updateEpisodeLabels(selectedEpisode.datasetId, selectedEpisode.episodeIndex, {
      caption: draft.caption.trim() || null,
      successLabel: draft.successLabel,
      failureReason: draft.failureReason.trim() || null,
      qualityScore: draft.qualityScore,
      split: draft.split || null,
      reviewStatus: draft.reviewStatus
    });
    setEpisodeRows((current) =>
      current.map((episode) =>
        episode.datasetId === updated.datasetId && episode.episodeIndex === updated.episodeIndex
          ? updated
          : episode
      )
    );
  }

  async function handleUpdateSegment(annotationId: string, draft: SegmentDraft) {
    const updated = await updateSegmentAnnotation(annotationId, {
      labelType: draft.labelType,
      labelValue: draft.labelValue,
      startFrame: draft.startFrame,
      endFrame: draft.endFrame,
      reviewStatus: "edited"
    });
    setAnnotationRows((current) =>
      current
        .map((annotation) => (annotation.id === annotationId ? updated : annotation))
        .sort((a, b) => a.startFrame - b.startFrame)
    );
  }

  async function handleSplitSegment(annotation: SegmentAnnotation) {
    if (annotation.endFrame <= annotation.startFrame) {
      return;
    }
    const splitFrame = Math.floor((annotation.startFrame + annotation.endFrame) / 2);
    const left = await createSegmentAnnotation({
      datasetId: annotation.datasetId,
      episodeIndex: annotation.episodeIndex,
      startFrame: annotation.startFrame,
      endFrame: splitFrame,
      labelType: annotation.labelType,
      labelValue: `${annotation.labelValue}_a`,
      source: "human",
      confidence: 1,
      reviewStatus: "edited"
    });
    const right = await createSegmentAnnotation({
      datasetId: annotation.datasetId,
      episodeIndex: annotation.episodeIndex,
      startFrame: splitFrame + 1,
      endFrame: annotation.endFrame,
      labelType: annotation.labelType,
      labelValue: `${annotation.labelValue}_b`,
      source: "human",
      confidence: 1,
      reviewStatus: "edited"
    });
    await deleteAnnotation(annotation.id);
    setAnnotationRows((current) =>
      [...current.filter((row) => row.id !== annotation.id), left, right].sort(
        (a, b) => a.startFrame - b.startFrame
      )
    );
  }

  async function handleMergeSegments(left: SegmentAnnotation, right: SegmentAnnotation) {
    const merged = await createSegmentAnnotation({
      datasetId: left.datasetId,
      episodeIndex: left.episodeIndex,
      startFrame: Math.min(left.startFrame, right.startFrame),
      endFrame: Math.max(left.endFrame, right.endFrame),
      labelType: left.labelType,
      labelValue: left.labelValue,
      source: "human",
      confidence: Math.max(left.confidence, right.confidence),
      reviewStatus: "edited"
    });
    await deleteAnnotation(left.id);
    await deleteAnnotation(right.id);
    setAnnotationRows((current) =>
      [
        ...current.filter((row) => row.id !== left.id && row.id !== right.id),
        merged
      ].sort((a, b) => a.startFrame - b.startFrame)
    );
  }

  async function handleUpdateReviewStatus(annotationId: string, status: ReviewStatus) {
    const updated = await updateAnnotationReviewStatus(annotationId, status);
    setAnnotationRows((current) =>
      current.map((annotation) => (annotation.id === annotationId ? updated : annotation))
    );
  }

  async function handleDeleteSegment(annotationId: string) {
    await deleteAnnotation(annotationId);
    setAnnotationRows((current) => current.filter((annotation) => annotation.id !== annotationId));
  }

  async function handleCreateRerunSession() {
    const session = await createRerunSession(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    setRerunSession(session);
  }

  async function handleRunVlmLabel() {
    const job = await createVlmLabelJob(selectedEpisode.datasetId, [selectedEpisode.episodeIndex]);
    const apiAnnotations = await fetchAnnotations(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    setVlmJob(job);
    setAnnotationRows(apiAnnotations);
  }

  async function handleSemanticSearch(text: string) {
    const results = await semanticSearch(selectedDatasetId, text);
    setSearchResults(results);
  }

  async function handleFullTextSearch(text: string) {
    const results = await fullTextSearch(selectedDatasetId, text);
    setSearchResults(results);
  }

  async function handleFilterSearch(query: string) {
    const results = await filterSearch(selectedDatasetId, query);
    setSearchResults(results);
  }

  async function handleCreateFilterPreset(name: string, query: string) {
    const preset = await createFilterPreset(selectedDatasetId, name, query);
    setFilterPresets((current) => [
      preset,
      ...current.filter((item) => item.presetId !== preset.presetId)
    ]);
  }

  async function handleDeleteFilterPreset(presetId: string) {
    await deleteFilterPreset(presetId);
    setFilterPresets((current) => current.filter((preset) => preset.presetId !== presetId));
  }

  async function handleCreateExport(format: "lerobot" | "lance" | "jsonl" | "vla" = "lerobot") {
    const record = await createExport(selectedEpisode.datasetId, [selectedEpisode.episodeIndex], format);
    setExportRecord(record);
  }

  async function handleUpdateSelectedFrameBadFlag(isBadFrame: boolean) {
    await handleUpdateSelectedFrameLabel("bad_frame", "bad_frame", isBadFrame);
  }

  async function handleUpdateSelectedFrameLabel(
    labelType: string,
    labelValue: string,
    labelEnabled: boolean,
  ) {
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const frameIndex = Math.max(0, Math.min(maxFrame, Math.round(selectedFrameIndex)));
    const updated = await updateFrameRecord(
      selectedEpisode.datasetId,
      selectedEpisode.episodeIndex,
      frameIndex,
      {
        labelType,
        labelValue,
        labelEnabled
      }
    );
    setSelectedFrameRecord(updated);
    setSelectedFrameStatus("ready");
    const apiAnnotations = await fetchAnnotations(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    setAnnotationRows(apiAnnotations);
  }

  return {
    annotationRows,
    dataStatus,
    episodeRows,
    exportRecord,
    filterPresets,
    rerunSession,
    rerunViewerUrl,
    searchResults,
    selectedEpisode,
    selectedEpisodeIndex,
    selectedFrameIndex,
    selectedFrameRecord,
    selectedFrameStatus,
    selectedSummary,
    vlmJob,
    handleCreateExport,
    handleCreateFilterPreset,
    handleCreateRerunSession,
    handleCreateSegment,
    handleDeleteSegment,
    handleDeleteFilterPreset,
    handleFilterSearch,
    handleFullTextSearch,
    handleMergeSegments,
    handleOpenDataset,
    handleRunVlmLabel,
    handleSelectEpisode,
    handleSelectFrame,
    handleSemanticSearch,
    handleSplitSegment,
    handleUpdateEpisodeLabels,
    handleUpdateSelectedFrameLabel,
    handleUpdateSelectedFrameBadFlag,
    handleUpdateReviewStatus,
    handleUpdateSegment
  };
}
