"use client";

import { useEffect, useMemo, useState } from "react";

import {
  createExport,
  createRerunSession,
  createSegmentAnnotation,
  createVlmLabelJob,
  deleteAnnotation,
  fetchAnnotations,
  fetchDatasetSummaries,
  fetchEpisodes,
  filterSearch,
  openDataset,
  semanticSearch,
  updateSegmentAnnotation,
  updateAnnotationReviewStatus
} from "@/lib/api";
import { annotations, datasetSummary, episodes } from "@/lib/sample-data";
import type {
  DatasetSummary,
  Episode,
  ExportRecord,
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

  function resetDerivedState() {
    setRerunSession(null);
    setVlmJob(null);
    setExportRecord(null);
    setSearchResults([]);
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
    setRerunSession(null);
    setVlmJob(null);
    setExportRecord(null);
  }

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

  async function handleFilterSearch(query: string) {
    const results = await filterSearch(selectedDatasetId, query);
    setSearchResults(results);
  }

  async function handleCreateExport() {
    const record = await createExport(selectedEpisode.datasetId, [selectedEpisode.episodeIndex]);
    setExportRecord(record);
  }

  return {
    annotationRows,
    dataStatus,
    episodeRows,
    exportRecord,
    rerunSession,
    rerunViewerUrl,
    searchResults,
    selectedEpisode,
    selectedEpisodeIndex,
    selectedSummary,
    vlmJob,
    handleCreateExport,
    handleCreateRerunSession,
    handleCreateSegment,
    handleDeleteSegment,
    handleFilterSearch,
    handleOpenDataset,
    handleRunVlmLabel,
    handleSelectEpisode,
    handleSemanticSearch,
    handleSplitSegment,
    handleUpdateReviewStatus,
    handleUpdateSegment
  };
}
