"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createExportJob,
  createFilterPreset,
  createRerunSessionJob,
  createSegmentAnnotation,
  createVlmLabelJob,
  deleteAnnotation,
  deleteFilterPreset,
  fetchAnnotations,
  fetchDatasetSummaries,
  fetchEpisodes,
  fetchExport,
  fetchFilterPresets,
  fetchFrameRecord,
  fetchFrameWindowPage,
  fetchRerunSession,
  filterSearch,
  fullTextSearch,
  openDataset,
  semanticSearch,
  streamJobEvents,
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
  FrameListPage,
  FrameRecord,
  JobProgressEvent,
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

const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed"]);

function sortAnnotations(rows: SegmentAnnotation[]): SegmentAnnotation[] {
  return [...rows].sort((a, b) => a.startFrame - b.startFrame);
}

function optimisticAnnotation(
  episode: Pick<Episode, "datasetId" | "episodeIndex">,
  draft: SegmentDraft,
  patch: Partial<SegmentAnnotation> = {},
): SegmentAnnotation {
  return {
    id: `optimistic-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    datasetId: episode.datasetId,
    episodeIndex: episode.episodeIndex,
    startFrame: draft.startFrame,
    endFrame: draft.endFrame,
    labelType: draft.labelType,
    labelValue: draft.labelValue,
    source: "human",
    confidence: 1,
    reviewStatus: "accepted",
    createdBy: "local",
    assignedTo: null,
    ...patch
  };
}

function mergeJobEvent(record: JobRecord, event: JobProgressEvent): JobRecord {
  return {
    ...record,
    kind: event.kind,
    status: event.status,
    progress: event.progress,
    message: event.message,
    queueJobId: event.queueJobId,
    createdExportId: event.createdExportId,
    exportFormat: event.exportFormat,
    exportUri: event.exportUri,
    createdRerunSessionId: event.createdRerunSessionId,
    rerunRrdUrl: event.rerunRrdUrl,
    rerunRrdPath: event.rerunRrdPath,
    rerunViewerUrl: event.rerunViewerUrl
  };
}

export function useStudioData() {
  const [summaries, setSummaries] = useState<DatasetSummary[]>([datasetSummary]);
  const [episodeRows, setEpisodeRows] = useState<Episode[]>(episodes);
  const [selectedDatasetId, setSelectedDatasetId] = useState(datasetSummary.datasetId);
  const [selectedEpisodeIndex, setSelectedEpisodeIndex] = useState(episodes[0].episodeIndex);
  const [annotationRows, setAnnotationRows] = useState<SegmentAnnotation[]>(annotations);
  const [rerunSession, setRerunSession] = useState<RerunSession | null>(null);
  const [rerunJob, setRerunJob] = useState<JobRecord | null>(null);
  const [vlmJob, setVlmJob] = useState<JobRecord | null>(null);
  const [exportJob, setExportJob] = useState<JobRecord | null>(null);
  const [exportRecord, setExportRecord] = useState<ExportRecord | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [filterPresets, setFilterPresets] = useState<FilterPreset[]>([]);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState(0);
  const [selectedFrameRecord, setSelectedFrameRecord] = useState<FrameRecord | null>(null);
  const [frameRows, setFrameRows] = useState<FrameRecord[]>([]);
  const [framePage, setFramePage] = useState<FrameListPage | null>(null);
  const [frameBrowserStart, setFrameBrowserStart] = useState(0);
  const [frameBrowserLimit, setFrameBrowserLimit] = useState(32);
  const [frameRowsStatus, setFrameRowsStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle"
  );
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
  const rerunJobId = rerunJob?.jobId ?? null;
  const rerunJobStatus = rerunJob?.status ?? null;
  const vlmJobId = vlmJob?.jobId ?? null;
  const vlmJobStatus = vlmJob?.status ?? null;
  const exportJobId = exportJob?.jobId ?? null;
  const exportJobStatus = exportJob?.status ?? null;

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
    setFrameRows([]);
    setFramePage(null);
    setFrameBrowserStart(0);
    setFrameRowsStatus("idle");
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
    annotationRows,
    selectedFrameIndex
  ]);

  useEffect(() => {
    if (selectedEpisode.length <= 0) {
      setFrameRows([]);
      setFramePage(null);
      setFrameRowsStatus("idle");
      return;
    }

    let isMounted = true;
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const startFrame = Math.max(
      0,
      Math.min(Math.round(frameBrowserStart), Math.max(0, maxFrame - frameBrowserLimit + 1))
    );
    const endFrame = Math.min(maxFrame, startFrame + frameBrowserLimit - 1);
    setFrameRowsStatus("loading");
    const timeoutId = window.setTimeout(() => {
      fetchFrameWindowPage(
        selectedEpisode.datasetId,
        selectedEpisode.episodeIndex,
        startFrame,
        endFrame,
        frameBrowserLimit
      )
        .then((page) => {
          if (isMounted) {
            setFramePage(page);
            setFrameRows(page.items);
            setFrameRowsStatus("ready");
          }
        })
        .catch(() => {
          if (isMounted) {
            setFrameRows([]);
            setFramePage(null);
            setFrameRowsStatus("error");
          }
        });
    }, 160);

    return () => {
      isMounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [
    selectedEpisode.datasetId,
    selectedEpisode.episodeIndex,
    selectedEpisode.length,
    annotationRows,
    frameBrowserLimit,
    frameBrowserStart
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

  useEffect(() => {
    if (!vlmJobId || !vlmJobStatus || TERMINAL_JOB_STATUSES.has(vlmJobStatus)) {
      return;
    }

    const jobId = vlmJobId;
    let isActive = true;
    const controller = new AbortController();
    streamJobEvents(
      jobId,
      (event) => {
        if (!isActive) {
          return;
        }
        setVlmJob((current) =>
          current?.jobId === event.jobId ? mergeJobEvent(current, event) : current
        );
        if (TERMINAL_JOB_STATUSES.has(event.status)) {
          fetchAnnotations(selectedEpisode.datasetId, selectedEpisode.episodeIndex)
            .then((apiAnnotations) => {
              if (isActive) {
                setAnnotationRows(apiAnnotations);
              }
            })
            .catch(() => undefined);
        }
      },
      controller.signal
    ).catch((error) => {
      if (isActive && error instanceof Error && error.name !== "AbortError") {
        setVlmJob((current) =>
          current?.jobId === jobId
            ? {
                ...current,
                status: "failed",
                progress: 1,
                message: error.message
              }
            : current
        );
      }
    });

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [selectedEpisode.datasetId, selectedEpisode.episodeIndex, vlmJobId, vlmJobStatus]);

  useEffect(() => {
    if (!rerunJobId || !rerunJobStatus || TERMINAL_JOB_STATUSES.has(rerunJobStatus)) {
      return;
    }

    const jobId = rerunJobId;
    let isActive = true;
    const controller = new AbortController();
    streamJobEvents(
      jobId,
      (event) => {
        if (!isActive) {
          return;
        }
        setRerunJob((current) =>
          current?.jobId === event.jobId ? mergeJobEvent(current, event) : current
        );
        if (TERMINAL_JOB_STATUSES.has(event.status) && event.createdRerunSessionId) {
          fetchRerunSession(event.createdRerunSessionId)
            .then((session) => {
              if (isActive) {
                setRerunSession(session);
              }
            })
            .catch(() => undefined);
        }
      },
      controller.signal
    ).catch((error) => {
      if (isActive && error instanceof Error && error.name !== "AbortError") {
        setRerunJob((current) =>
          current?.jobId === jobId
            ? {
                ...current,
                status: "failed",
                progress: 1,
                message: error.message
              }
            : current
        );
      }
    });

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [rerunJobId, rerunJobStatus]);

  useEffect(() => {
    if (!exportJobId || !exportJobStatus || TERMINAL_JOB_STATUSES.has(exportJobStatus)) {
      return;
    }

    const jobId = exportJobId;
    let isActive = true;
    const controller = new AbortController();
    streamJobEvents(
      jobId,
      (event) => {
        if (!isActive) {
          return;
        }
        setExportJob((current) =>
          current?.jobId === event.jobId ? mergeJobEvent(current, event) : current
        );
        if (TERMINAL_JOB_STATUSES.has(event.status) && event.createdExportId) {
          fetchExport(event.createdExportId)
            .then((record) => {
              if (isActive) {
                setExportRecord(record);
              }
            })
            .catch(() => undefined);
        }
      },
      controller.signal
    ).catch((error) => {
      if (isActive && error instanceof Error && error.name !== "AbortError") {
        setExportJob((current) =>
          current?.jobId === jobId
            ? {
                ...current,
                status: "failed",
                progress: 1,
                message: error.message
              }
            : current
        );
      }
    });

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [exportJobId, exportJobStatus]);

  function resetDerivedState() {
    setRerunSession(null);
    setRerunJob(null);
    setVlmJob(null);
    setExportJob(null);
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
    setFrameRows([]);
    setFramePage(null);
    setFrameBrowserStart(0);
    setFrameRowsStatus("idle");
    setSelectedFrameStatus("idle");
    setRerunSession(null);
    setVlmJob(null);
    setExportRecord(null);
  }

  const handleSelectFrame = useCallback((frameIndex: number) => {
    setSelectedFrameIndex(Math.max(0, Math.round(frameIndex)));
  }, []);

  useEffect(() => {
    if (selectedEpisode.length <= 0) {
      return;
    }
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const frameIndex = Math.max(0, Math.min(maxFrame, Math.round(selectedFrameIndex)));
    if (
      frameIndex < frameBrowserStart ||
      frameIndex >= frameBrowserStart + frameBrowserLimit
    ) {
      const maxStart = Math.max(0, maxFrame - frameBrowserLimit + 1);
      const pageStart = Math.floor(frameIndex / frameBrowserLimit) * frameBrowserLimit;
      setFrameBrowserStart(Math.max(0, Math.min(pageStart, maxStart)));
    }
  }, [frameBrowserLimit, frameBrowserStart, selectedEpisode.length, selectedFrameIndex]);

  const handleSetFrameBrowserStart = useCallback(
    (startFrame: number) => {
      const maxFrame = Math.max(0, selectedEpisode.length - 1);
      const maxStart = Math.max(0, maxFrame - frameBrowserLimit + 1);
      setFrameBrowserStart(Math.max(0, Math.min(Math.round(startFrame), maxStart)));
    },
    [frameBrowserLimit, selectedEpisode.length]
  );

  const handleSetFrameBrowserLimit = useCallback(
    (limit: number) => {
      const nextLimit = Math.max(8, Math.min(128, Math.round(limit)));
      const maxFrame = Math.max(0, selectedEpisode.length - 1);
      const maxStart = Math.max(0, maxFrame - nextLimit + 1);
      const nextStart = Math.floor(Math.max(0, selectedFrameIndex) / nextLimit) * nextLimit;
      setFrameBrowserLimit(nextLimit);
      setFrameBrowserStart(Math.max(0, Math.min(nextStart, maxStart)));
    },
    [selectedEpisode.length, selectedFrameIndex]
  );

  async function handleCreateSegment(draft: SegmentDraft) {
    const previousAnnotations = annotationRows;
    const optimistic = optimisticAnnotation(selectedEpisode, draft);
    setAnnotationRows((current) => sortAnnotations([...current, optimistic]));
    try {
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
      setAnnotationRows((current) =>
        sortAnnotations(current.map((annotation) => (annotation.id === optimistic.id ? created : annotation)))
      );
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleUpdateEpisodeLabels(draft: EpisodeLabelDraft) {
    const previousEpisode = selectedEpisode;
    const optimisticEpisode: Episode = {
      ...selectedEpisode,
      caption: draft.caption.trim(),
      successLabel: draft.successLabel,
      failureReason: draft.failureReason.trim(),
      qualityScore: draft.qualityScore,
      split: draft.split,
      reviewStatus: draft.reviewStatus,
      hasHumanLabel: true
    };
    setEpisodeRows((current) =>
      current.map((episode) =>
        episode.datasetId === optimisticEpisode.datasetId &&
        episode.episodeIndex === optimisticEpisode.episodeIndex
          ? optimisticEpisode
          : episode
      )
    );
    try {
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
    } catch (error) {
      setEpisodeRows((current) =>
        current.map((episode) =>
          episode.datasetId === previousEpisode.datasetId &&
          episode.episodeIndex === previousEpisode.episodeIndex
            ? previousEpisode
            : episode
        )
      );
      throw error;
    }
  }

  async function handleUpdateSegment(annotationId: string, draft: SegmentDraft) {
    const previousAnnotations = annotationRows;
    const existing = annotationRows.find((annotation) => annotation.id === annotationId);
    if (existing) {
      setAnnotationRows((current) =>
        sortAnnotations(
          current.map((annotation) =>
            annotation.id === annotationId
              ? {
                  ...annotation,
                  labelType: draft.labelType,
                  labelValue: draft.labelValue,
                  startFrame: draft.startFrame,
                  endFrame: draft.endFrame,
                  reviewStatus: "edited"
                }
              : annotation
          )
        )
      );
    }
    try {
      const updated = await updateSegmentAnnotation(annotationId, {
        labelType: draft.labelType,
        labelValue: draft.labelValue,
        startFrame: draft.startFrame,
        endFrame: draft.endFrame,
        reviewStatus: "edited"
      });
      setAnnotationRows((current) =>
        sortAnnotations(current.map((annotation) => (annotation.id === annotationId ? updated : annotation)))
      );
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleSplitSegment(annotation: SegmentAnnotation) {
    if (annotation.endFrame <= annotation.startFrame) {
      return;
    }
    const splitFrame = Math.floor((annotation.startFrame + annotation.endFrame) / 2);
    const previousAnnotations = annotationRows;
    const leftDraft = {
      startFrame: annotation.startFrame,
      endFrame: splitFrame,
      labelType: annotation.labelType,
      labelValue: `${annotation.labelValue}_a`
    };
    const rightDraft = {
      startFrame: splitFrame + 1,
      endFrame: annotation.endFrame,
      labelType: annotation.labelType,
      labelValue: `${annotation.labelValue}_b`
    };
    const leftOptimistic = optimisticAnnotation(annotation, leftDraft, { reviewStatus: "edited" });
    const rightOptimistic = optimisticAnnotation(annotation, rightDraft, { reviewStatus: "edited" });
    setAnnotationRows((current) =>
      sortAnnotations([
        ...current.filter((row) => row.id !== annotation.id),
        leftOptimistic,
        rightOptimistic
      ])
    );
    try {
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
        sortAnnotations([
          ...current.filter(
            (row) => row.id !== leftOptimistic.id && row.id !== rightOptimistic.id
          ),
          left,
          right
        ])
      );
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleMergeSegments(left: SegmentAnnotation, right: SegmentAnnotation) {
    const previousAnnotations = annotationRows;
    const mergedDraft = {
      startFrame: Math.min(left.startFrame, right.startFrame),
      endFrame: Math.max(left.endFrame, right.endFrame),
      labelType: left.labelType,
      labelValue: left.labelValue
    };
    const mergedOptimistic = optimisticAnnotation(left, mergedDraft, {
      confidence: Math.max(left.confidence, right.confidence),
      reviewStatus: "edited"
    });
    setAnnotationRows((current) =>
      sortAnnotations([
        ...current.filter((row) => row.id !== left.id && row.id !== right.id),
        mergedOptimistic
      ])
    );
    try {
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
        sortAnnotations([
          ...current.filter((row) => row.id !== mergedOptimistic.id),
          merged
        ])
      );
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleUpdateReviewStatus(annotationId: string, status: ReviewStatus) {
    const previousAnnotations = annotationRows;
    setAnnotationRows((current) =>
      current.map((annotation) =>
        annotation.id === annotationId ? { ...annotation, reviewStatus: status } : annotation
      )
    );
    try {
      const updated = await updateAnnotationReviewStatus(annotationId, status);
      setAnnotationRows((current) =>
        current.map((annotation) => (annotation.id === annotationId ? updated : annotation))
      );
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleDeleteSegment(annotationId: string) {
    const previousAnnotations = annotationRows;
    setAnnotationRows((current) => current.filter((annotation) => annotation.id !== annotationId));
    try {
      await deleteAnnotation(annotationId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      throw error;
    }
  }

  async function handleCreateRerunSession() {
    const job = await createRerunSessionJob(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    setRerunJob(job);
    if (TERMINAL_JOB_STATUSES.has(job.status) && job.createdRerunSessionId) {
      const session = await fetchRerunSession(job.createdRerunSessionId);
      setRerunSession(session);
    }
  }

  async function handleRunVlmLabel() {
    const job = await createVlmLabelJob(selectedEpisode.datasetId, [selectedEpisode.episodeIndex]);
    setVlmJob(job);
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      const apiAnnotations = await fetchAnnotations(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
      setAnnotationRows(apiAnnotations);
    }
  }

  async function handleSemanticSearch(text: string, filterQuery?: string) {
    const results = await semanticSearch(selectedDatasetId, text, filterQuery);
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

  async function handleCreateExport(
    format: "lerobot" | "lance" | "jsonl" | "vla" = "lerobot",
    scope: "episode" | "split" = "episode",
  ) {
    const split = selectedEpisode.split || null;
    const splits = scope === "split" && split ? [split] : [];
    const episodeIndices = splits.length > 0 ? [] : [selectedEpisode.episodeIndex];
    const job = await createExportJob(selectedEpisode.datasetId, episodeIndices, format, splits);
    setExportJob(job);
    if (TERMINAL_JOB_STATUSES.has(job.status) && job.createdExportId) {
      const record = await fetchExport(job.createdExportId);
      setExportRecord(record);
    }
  }

  async function handleUpdateSelectedFrameBadFlag(isBadFrame: boolean) {
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const frameIndex = Math.max(0, Math.min(maxFrame, Math.round(selectedFrameIndex)));
    await handleUpdateFrameLabel(frameIndex, "bad_frame", "bad_frame", isBadFrame);
  }

  async function handleUpdateSelectedFrameLabel(
    labelType: string,
    labelValue: string,
    labelEnabled: boolean,
  ) {
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const frameIndex = Math.max(0, Math.min(maxFrame, Math.round(selectedFrameIndex)));
    await handleUpdateFrameLabel(frameIndex, labelType, labelValue, labelEnabled);
  }

  async function handleUpdateFrameBadFlag(frameIndex: number, isBadFrame: boolean) {
    await handleUpdateFrameLabel(frameIndex, "bad_frame", "bad_frame", isBadFrame);
  }

  async function handleUpdateFrameLabel(
    frameIndex: number,
    labelType: string,
    labelValue: string,
    labelEnabled: boolean,
  ) {
    const maxFrame = Math.max(0, selectedEpisode.length - 1);
    const boundedFrameIndex = Math.max(0, Math.min(maxFrame, Math.round(frameIndex)));
    const updated = await updateFrameRecord(
      selectedEpisode.datasetId,
      selectedEpisode.episodeIndex,
      boundedFrameIndex,
      {
        labelType,
        labelValue,
        labelEnabled
      }
    );
    if (updated.frameIndex === Math.round(selectedFrameIndex)) {
      setSelectedFrameRecord(updated);
    }
    setFrameRows((current) =>
      current.map((frame) => (frame.frameIndex === updated.frameIndex ? updated : frame))
    );
    setFramePage((current) =>
      current
        ? {
            ...current,
            items: current.items.map((frame) =>
              frame.frameIndex === updated.frameIndex ? updated : frame
            )
          }
        : current
    );
    setSelectedFrameStatus("ready");
    const apiAnnotations = await fetchAnnotations(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    setAnnotationRows(apiAnnotations);
  }

  return {
    annotationRows,
    dataStatus,
    episodeRows,
    exportJob,
    exportRecord,
    filterPresets,
    frameBrowserLimit,
    frameBrowserStart,
    framePage,
    frameRows,
    frameRowsStatus,
    rerunJob,
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
    handleUpdateFrameBadFlag,
    handleSetFrameBrowserLimit,
    handleSetFrameBrowserStart,
    handleUpdateSelectedFrameLabel,
    handleUpdateSelectedFrameBadFlag,
    handleUpdateReviewStatus,
    handleUpdateSegment
  };
}
