"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiConflictError,
  assignAnnotation,
  createExportJob,
  createFilterPreset,
  createRerunSessionJob,
  createSegmentAnnotation,
  createVlmLabelJob,
  deleteAnnotation,
  deleteFilterPreset,
  fetchAnnotationHistory,
  fetchAnnotations,
  fetchCurrentUser,
  fetchDatasetHealth,
  fetchDatasetSummaries,
  fetchEpisodePage,
  fetchExport,
  listExports,
  fetchFilterPresets,
  fetchFrameRecord,
  fetchFrameWindowPage,
  fetchRerunSession,
  fetchVlmResponses,
  filterSearch,
  fullTextSearch,
  openDataset,
  semanticSearch,
  setEpisodeDisposition,
  streamJobEvents,
  updateSegmentAnnotation,
  updateAnnotationReviewStatus,
  updateFrameRecord,
  uploadExportToHub
} from "@/lib/api";
import { annotationHistory, annotations, datasetSummary, episodes } from "@/lib/sample-data";
import { SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type {
  AnnotationHistoryRecord,
  DatasetHealth,
  DatasetSummary,
  Episode,
  EpisodeDisposition,
  EpisodeMetadataFilters,
  ExportHubUploadResult,
  ExportRecord,
  ExportFormat,
  FilterPreset,
  FrameListPage,
  FrameRecord,
  JobProgressEvent,
  JobRecord,
  RerunSession,
  ReviewStatus,
  SearchResult,
  SegmentAnnotation,
  SkillExportOptions,
  VlmResponseRecord
} from "@/lib/types";

type SegmentDraft = {
  labelType: string;
  labelValue: string;
  startFrame: number;
  endFrame: number;
  reviewStatus?: ReviewStatus;
  metadata?: SegmentAnnotation["metadata"];
};

const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed"]);
const EPISODE_PAGE_LIMIT = 1000;
const DEFAULT_EPISODE_METADATA_FILTERS: EpisodeMetadataFilters = {
  instruction: "all",
  wristCamera: "all"
};

function episodePageFilterQuery(
  filters: EpisodeMetadataFilters,
  searchText: string
): string | undefined {
  const clauses: string[] = [];
  const query = searchText.trim();
  if (query) {
    clauses.push(`instruction_text contains ${filterQueryLiteral(query)}`);
  }
  if (filters.instruction === "with_instruction") {
    clauses.push("has_instruction == true");
  } else if (filters.instruction === "without_instruction") {
    clauses.push("has_instruction == false");
  }
  if (filters.wristCamera === "with_wrist") {
    clauses.push("has_wrist_camera == true");
  } else if (filters.wristCamera === "without_wrist") {
    clauses.push("has_wrist_camera == false");
  }
  return clauses.length > 0 ? clauses.join(" AND ") : undefined;
}

function filterQueryLiteral(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function sortAnnotations(rows: SegmentAnnotation[]): SegmentAnnotation[] {
  return [...rows].sort((a, b) => a.startFrame - b.startFrame);
}

function canMergeAnnotations(
  left: SegmentAnnotation,
  right: SegmentAnnotation | null,
): right is SegmentAnnotation {
  if (right === null) {
    return false;
  }
  if (left.datasetId !== right.datasetId || left.episodeIndex !== right.episodeIndex) {
    return false;
  }
  if (left.labelType !== right.labelType) {
    return false;
  }
  if (left.labelType === SKILL_LABEL_TYPE) {
    return left.labelValue === right.labelValue;
  }
  return true;
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
    reviewStatus: draft.reviewStatus ?? "accepted",
    metadata: draft.metadata ?? {},
    createdBy: "local",
    updatedBy: "local",
    assignedTo: null,
    revision: 1,
    deletedAt: null,
    lockOwner: null,
    lockExpiresAt: null,
    appliedExportId: null,
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
    rawResponseIds: event.rawResponseIds,
    rawResponseUri: event.rawResponseUri,
    createdExportId: event.createdExportId,
    exportFormat: event.exportFormat,
    exportUri: event.exportUri,
    createdRerunSessionId: event.createdRerunSessionId,
    rerunRrdUrl: event.rerunRrdUrl,
    rerunRrdPath: event.rerunRrdPath,
    rerunPublishedUri: event.rerunPublishedUri,
    rerunViewerUrl: event.rerunViewerUrl
  };
}

export function useStudioData() {
  const [summaries, setSummaries] = useState<DatasetSummary[]>([datasetSummary]);
  const [episodeRows, setEpisodeRows] = useState<Episode[]>(episodes);
  const [episodeTotal, setEpisodeTotal] = useState(episodes.length);
  const [episodeNextOffset, setEpisodeNextOffset] = useState<number | null>(null);
  const [episodeListStatus, setEpisodeListStatus] = useState<
    "idle" | "loading" | "loading_more" | "ready" | "error"
  >("idle");
  const [episodeMetadataFilters, setEpisodeMetadataFilters] =
    useState<EpisodeMetadataFilters>(DEFAULT_EPISODE_METADATA_FILTERS);
  const [episodeSearchText, setEpisodeSearchText] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState(datasetSummary.datasetId);
  const [selectedEpisodeIndex, setSelectedEpisodeIndex] = useState(episodes[0].episodeIndex);
  const [annotationRows, setAnnotationRows] = useState<SegmentAnnotation[]>(annotations);
  const [annotationHistoryRows, setAnnotationHistoryRows] =
    useState<AnnotationHistoryRecord[]>(annotationHistory);
  const [reviewQueueRows, setReviewQueueRows] = useState<SegmentAnnotation[]>(annotations);
  const [reviewerUserId, setReviewerUserId] = useState("local");
  const [rerunSession, setRerunSession] = useState<RerunSession | null>(null);
  const [rerunJob, setRerunJob] = useState<JobRecord | null>(null);
  const [vlmJob, setVlmJob] = useState<JobRecord | null>(null);
  const [vlmResponses, setVlmResponses] = useState<VlmResponseRecord[]>([]);
  const [exportJob, setExportJob] = useState<JobRecord | null>(null);
  const [exportRecord, setExportRecord] = useState<ExportRecord | null>(null);
  const [pastExports, setPastExports] = useState<ExportRecord[]>([]);
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
  const [selectedDatasetHealth, setSelectedDatasetHealth] = useState<DatasetHealth | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);

  const selectedSummary =
    summaries.find((summary) => summary.datasetId === selectedDatasetId) ??
    summaries[0] ??
    datasetSummary;

  const selectedEpisode = useMemo(() => {
    const matched =
      episodeRows.find((episode) => episode.episodeIndex === selectedEpisodeIndex) ??
      episodeRows[0];
    if (matched) {
      return matched;
    }
    return {
      ...episodes[0],
      datasetId: selectedDatasetId,
      episodeIndex: selectedEpisodeIndex,
      taskIndex: 0,
      length: 0,
      successLabel: null,
      qualityScore: null,
      reviewStatus: "pending" as const,
      caption: "No episode matches the current filters.",
      failureReason: "",
      hasVlmLabel: false,
      hasHumanLabel: false,
      split: null,
      fps: 0,
      cameraNames: [],
      languageInstruction: null,
      hasInstruction: false,
      hasWristCamera: false,
      taskSegments: [],
      dirtyAnnotationCount: 0
    };
  }, [episodeRows, selectedDatasetId, selectedEpisodeIndex]);

  const rerunViewerUrl = process.env.NEXT_PUBLIC_RERUN_IFRAME_URL ?? null;
  const rerunJobId = rerunJob?.jobId ?? null;
  const rerunJobStatus = rerunJob?.status ?? null;
  const vlmJobId = vlmJob?.jobId ?? null;
  const vlmJobStatus = vlmJob?.status ?? null;
  const exportJobId = exportJob?.jobId ?? null;
  const exportJobStatus = exportJob?.status ?? null;

  const refreshAnnotationHistory = useCallback(async (datasetId: string, episodeIndex: number) => {
    try {
      const history = await fetchAnnotationHistory(datasetId, episodeIndex);
      setAnnotationHistoryRows(history);
    } catch {
      setAnnotationHistoryRows(
        annotationHistory.filter(
          (event) => event.datasetId === datasetId && event.episodeIndex === episodeIndex
        )
      );
    }
  }, []);

  const refreshReviewQueue = useCallback(async (datasetId: string) => {
    try {
      const rows = await fetchAnnotations(datasetId);
      setReviewQueueRows(rows);
    } catch {
      setReviewQueueRows(annotations.filter((annotation) => annotation.datasetId === datasetId));
    }
  }, []);

  const loadEpisodePage = useCallback(
    async (
      datasetId: string,
      offset = 0,
      append = false,
      filters: EpisodeMetadataFilters = DEFAULT_EPISODE_METADATA_FILTERS,
      searchText = ""
    ) => {
      setEpisodeListStatus(append ? "loading_more" : "loading");
      try {
        const page = await fetchEpisodePage(datasetId, {
          limit: EPISODE_PAGE_LIMIT,
          offset,
          filterQuery: episodePageFilterQuery(filters, searchText)
        });
        setEpisodeRows((current) => {
          if (!append) {
            return page.items;
          }
          const seen = new Set(current.map((episode) => episode.episodeIndex));
          const nextItems = page.items.filter((episode) => !seen.has(episode.episodeIndex));
          return [...current, ...nextItems];
        });
        setEpisodeTotal(page.total);
        setEpisodeNextOffset(page.nextOffset);
        setEpisodeListStatus("ready");
        return page;
      } catch (error) {
        setEpisodeListStatus("error");
        throw error;
      }
    },
    []
  );

  const handleAnnotationMutationError = useCallback(
    async (error: unknown, datasetId: string, episodeIndex: number) => {
      if (!(error instanceof ApiConflictError)) {
        return;
      }
      setMutationNotice("Annotation changed on the server. Refreshed the episode; review and retry.");
      try {
        const rows = await fetchAnnotations(datasetId, episodeIndex);
        setAnnotationRows(rows);
        await refreshAnnotationHistory(datasetId, episodeIndex);
        await refreshReviewQueue(datasetId);
      } catch {
        // Keep the rollback state if the refresh also fails.
      }
    },
    [refreshAnnotationHistory, refreshReviewQueue]
  );

  useEffect(() => {
    let isMounted = true;

    fetchCurrentUser()
      .then((identity) => {
        if (isMounted) {
          setReviewerUserId(identity.userId);
        }
      })
      .catch(() => {
        if (isMounted) {
          setReviewerUserId("local");
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadInitialData() {
      try {
        const apiSummaries = await fetchDatasetSummaries();
        if (!isMounted || apiSummaries.length === 0) {
          return;
        }
        const defaultDatasetUri = process.env.NEXT_PUBLIC_DEFAULT_DATASET_URI ?? "";
        const preferredSummary =
          apiSummaries.find((summary) => summary.uri === defaultDatasetUri) ??
          apiSummaries.find((summary) => !summary.uri.startsWith("sample://")) ??
          apiSummaries[0];
        const datasetId = preferredSummary.datasetId;
        const page = await loadEpisodePage(datasetId);
        if (!isMounted) {
          return;
        }
        setSummaries(apiSummaries);
        setSelectedDatasetId(datasetId);
        setSelectedEpisodeIndex(page.items[0]?.episodeIndex ?? -1);
        resetDerivedState();
        setDataStatus("api");
      } catch {
        if (!isMounted) {
          return;
        }
        setSummaries([datasetSummary]);
        setSelectedDatasetId(datasetSummary.datasetId);
        setEpisodeRows(episodes);
        setEpisodeTotal(episodes.length);
        setEpisodeNextOffset(null);
        setEpisodeListStatus("ready");
        setEpisodeMetadataFilters(DEFAULT_EPISODE_METADATA_FILTERS);
        setEpisodeSearchText("");
        setSelectedEpisodeIndex(episodes[0].episodeIndex);
        resetDerivedState();
        setDataStatus("sample");
      }
    }

    loadInitialData();
    return () => {
      isMounted = false;
    };
  }, [loadEpisodePage]);

  useEffect(() => {
    if (dataStatus !== "api" || !selectedDatasetId) {
      setSelectedDatasetHealth(null);
      return;
    }

    let isMounted = true;
    fetchDatasetHealth(selectedDatasetId)
      .then((health) => {
        if (isMounted) {
          setSelectedDatasetHealth(health);
        }
      })
      .catch(() => {
        if (isMounted) {
          setSelectedDatasetHealth(null);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [dataStatus, selectedDatasetId]);

  useEffect(() => {
    void refreshReviewQueue(selectedDatasetId);
  }, [refreshReviewQueue, selectedDatasetId]);

  useEffect(() => {
    let isMounted = true;

    async function loadAnnotationsAndHistory() {
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
      try {
        const apiHistory = await fetchAnnotationHistory(
          selectedEpisode.datasetId,
          selectedEpisode.episodeIndex
        );
        if (isMounted) {
          setAnnotationHistoryRows(apiHistory);
        }
      } catch {
        if (isMounted) {
          setAnnotationHistoryRows(
            annotationHistory.filter(
              (event) =>
                event.datasetId === selectedEpisode.datasetId &&
                event.episodeIndex === selectedEpisode.episodeIndex
            )
          );
        }
      }
    }

    loadAnnotationsAndHistory();
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

  const refreshPastExports = useCallback(async (datasetId: string) => {
    try {
      const records = await listExports(datasetId);
      setPastExports(records);
    } catch {
      setPastExports([]);
    }
  }, []);

  useEffect(() => {
    if (!selectedDatasetId) {
      setPastExports([]);
      return;
    }
    void refreshPastExports(selectedDatasetId);
  }, [selectedDatasetId, refreshPastExports]);

  useEffect(() => {
    if (!vlmJobId || (vlmJob?.rawResponseIds.length ?? 0) === 0) {
      setVlmResponses([]);
      return;
    }

    let isMounted = true;
    fetchVlmResponses(vlmJobId)
      .then((responses) => {
        if (isMounted) {
          setVlmResponses(responses);
        }
      })
      .catch(() => {
        if (isMounted) {
          setVlmResponses([]);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [vlmJob?.rawResponseIds.length, vlmJobId, vlmJobStatus]);

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
                void refreshAnnotationHistory(
                  selectedEpisode.datasetId,
                  selectedEpisode.episodeIndex
                );
                void refreshReviewQueue(selectedEpisode.datasetId);
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
  }, [
    refreshAnnotationHistory,
    refreshReviewQueue,
    selectedEpisode.datasetId,
    selectedEpisode.episodeIndex,
    vlmJobId,
    vlmJobStatus
  ]);

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
    setVlmResponses([]);
    setExportJob(null);
    setExportRecord(null);
    setSearchResults([]);
    setFilterPresets([]);
    setAnnotationHistoryRows([]);
    setReviewQueueRows([]);
    setSelectedDatasetHealth(null);
  }

  async function handleOpenDataset(uri: string) {
    const summary = await openDataset(uri);
    setEpisodeMetadataFilters(DEFAULT_EPISODE_METADATA_FILTERS);
    setEpisodeSearchText("");
    const page = await loadEpisodePage(
      summary.datasetId,
      0,
      false,
      DEFAULT_EPISODE_METADATA_FILTERS,
      ""
    );
    setSummaries((current) => {
      const existing = current.filter((item) => item.datasetId !== summary.datasetId);
      return [summary, ...existing];
    });
    setSelectedDatasetId(summary.datasetId);
    setSelectedEpisodeIndex(page.items[0]?.episodeIndex ?? -1);
    resetDerivedState();
    setDataStatus("api");
  }

  async function handleSelectDataset(datasetId: string) {
    if (datasetId === selectedDatasetId) {
      return;
    }
    setEpisodeMetadataFilters(DEFAULT_EPISODE_METADATA_FILTERS);
    setEpisodeSearchText("");
    const page = await loadEpisodePage(datasetId, 0, false, DEFAULT_EPISODE_METADATA_FILTERS, "");
    setSelectedDatasetId(datasetId);
    setSelectedEpisodeIndex(page.items[0]?.episodeIndex ?? -1);
    resetDerivedState();
    setDataStatus("api");
  }

  async function handleLoadMoreEpisodes() {
    if (
      dataStatus !== "api" ||
      episodeNextOffset === null ||
      episodeListStatus === "loading" ||
      episodeListStatus === "loading_more"
    ) {
      return;
    }
    await loadEpisodePage(
      selectedDatasetId,
      episodeNextOffset,
      true,
      episodeMetadataFilters,
      episodeSearchText
    );
  }

  async function handleEpisodeMetadataFiltersChange(filters: EpisodeMetadataFilters) {
    setEpisodeMetadataFilters(filters);
    if (dataStatus !== "api") {
      return;
    }
    const page = await loadEpisodePage(selectedDatasetId, 0, false, filters, episodeSearchText);
    setSelectedEpisodeIndex(page.items[0]?.episodeIndex ?? -1);
    resetDerivedState();
  }

  async function handleEpisodeSearchTextChange(text: string) {
    const nextText = text.trim();
    setEpisodeSearchText(nextText);
    if (dataStatus !== "api") {
      return;
    }
    const page = await loadEpisodePage(
      selectedDatasetId,
      0,
      false,
      episodeMetadataFilters,
      nextText
    );
    setSelectedEpisodeIndex(page.items[0]?.episodeIndex ?? -1);
    resetDerivedState();
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
    setVlmResponses([]);
    setExportRecord(null);
    setAnnotationHistoryRows([]);
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
        reviewStatus: draft.reviewStatus ?? "accepted",
        metadata: draft.metadata
      });
      setAnnotationRows((current) =>
        sortAnnotations(current.map((annotation) => (annotation.id === optimistic.id ? created : annotation)))
      );
      await refreshAnnotationHistory(created.datasetId, created.episodeIndex);
      await refreshReviewQueue(created.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(error, selectedEpisode.datasetId, selectedEpisode.episodeIndex);
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
                  reviewStatus: draft.reviewStatus ?? "edited",
                  metadata: draft.metadata ?? annotation.metadata
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
        reviewStatus: draft.reviewStatus ?? "edited",
        expectedRevision: existing?.revision,
        metadata: draft.metadata
      });
      setAnnotationRows((current) =>
        sortAnnotations(current.map((annotation) => (annotation.id === annotationId ? updated : annotation)))
      );
      await refreshAnnotationHistory(updated.datasetId, updated.episodeIndex);
      await refreshReviewQueue(updated.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(
        error,
        existing?.datasetId ?? selectedEpisode.datasetId,
        existing?.episodeIndex ?? selectedEpisode.episodeIndex,
      );
      throw error;
    }
  }

  async function handleSplitSegment(annotation: SegmentAnnotation) {
    if (annotation.endFrame <= annotation.startFrame) {
      return;
    }
    const splitFrame = Math.floor((annotation.startFrame + annotation.endFrame) / 2);
    const previousAnnotations = annotationRows;
    const isSkillClip = annotation.labelType === SKILL_LABEL_TYPE;
    const leftLabelValue = isSkillClip ? annotation.labelValue : `${annotation.labelValue}_a`;
    const rightLabelValue = isSkillClip ? annotation.labelValue : `${annotation.labelValue}_b`;
    const leftDraft = {
      startFrame: annotation.startFrame,
      endFrame: splitFrame,
      labelType: annotation.labelType,
      labelValue: leftLabelValue,
      metadata: annotation.metadata
    };
    const rightDraft = {
      startFrame: splitFrame + 1,
      endFrame: annotation.endFrame,
      labelType: annotation.labelType,
      labelValue: rightLabelValue,
      metadata: annotation.metadata
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
        labelValue: leftLabelValue,
        source: "human",
        confidence: 1,
        reviewStatus: "edited",
        metadata: annotation.metadata
      });
      const right = await createSegmentAnnotation({
        datasetId: annotation.datasetId,
        episodeIndex: annotation.episodeIndex,
        startFrame: splitFrame + 1,
        endFrame: annotation.endFrame,
        labelType: annotation.labelType,
        labelValue: rightLabelValue,
        source: "human",
        confidence: 1,
        reviewStatus: "edited",
        metadata: annotation.metadata
      });
      await deleteAnnotation(annotation.id, annotation.revision);
      setAnnotationRows((current) =>
        sortAnnotations([
          ...current.filter(
            (row) => row.id !== leftOptimistic.id && row.id !== rightOptimistic.id
          ),
          left,
          right
        ])
      );
      await refreshAnnotationHistory(annotation.datasetId, annotation.episodeIndex);
      await refreshReviewQueue(annotation.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(error, annotation.datasetId, annotation.episodeIndex);
      throw error;
    }
  }

  async function handleMergeSegments(left: SegmentAnnotation, right: SegmentAnnotation) {
    if (!canMergeAnnotations(left, right)) {
      return;
    }
    const previousAnnotations = annotationRows;
    const mergedDraft = {
      startFrame: Math.min(left.startFrame, right.startFrame),
      endFrame: Math.max(left.endFrame, right.endFrame),
      labelType: left.labelType,
      labelValue: left.labelValue,
      metadata: left.metadata
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
        reviewStatus: "edited",
        metadata: left.metadata
      });
      await deleteAnnotation(left.id, left.revision);
      await deleteAnnotation(right.id, right.revision);
      setAnnotationRows((current) =>
        sortAnnotations([
          ...current.filter((row) => row.id !== mergedOptimistic.id),
          merged
        ])
      );
      await refreshAnnotationHistory(left.datasetId, left.episodeIndex);
      await refreshReviewQueue(left.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(error, selectedEpisode.datasetId, selectedEpisode.episodeIndex);
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
      const existing = annotationRows.find((annotation) => annotation.id === annotationId);
      const updated = await updateAnnotationReviewStatus(annotationId, status, existing?.revision);
      setAnnotationRows((current) =>
        current.map((annotation) => (annotation.id === annotationId ? updated : annotation))
      );
      await refreshAnnotationHistory(updated.datasetId, updated.episodeIndex);
      await refreshReviewQueue(updated.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(error, selectedEpisode.datasetId, selectedEpisode.episodeIndex);
      throw error;
    }
  }

  async function handleSetEpisodeDisposition(
    episodeIndex: number,
    disposition: EpisodeDisposition | null,
    reason: string | null,
  ): Promise<void> {
    const previousRows = episodeRows;
    const datasetId = selectedEpisode.datasetId;
    const optimisticPatch: Pick<
      Episode,
      "disposition" | "dispositionReason" | "dispositionUpdatedAt"
    > = {
      disposition,
      dispositionReason: disposition === null ? null : reason,
      dispositionUpdatedAt: new Date().toISOString()
    };
    setEpisodeRows((current) =>
      current.map((episode) =>
        episode.episodeIndex === episodeIndex && episode.datasetId === datasetId
          ? { ...episode, ...optimisticPatch }
          : episode
      )
    );
    try {
      const updated = await setEpisodeDisposition(datasetId, episodeIndex, disposition, reason);
      setEpisodeRows((current) =>
        current.map((episode) =>
          episode.episodeIndex === episodeIndex && episode.datasetId === datasetId
            ? { ...episode, ...updated }
            : episode
        )
      );
    } catch (error) {
      setEpisodeRows(previousRows);
      const message = error instanceof Error ? error.message : "Unknown error";
      setMutationNotice(`Failed to update episode disposition: ${message}`);
      throw error;
    }
  }

  async function handleAssignAnnotation(annotationId: string, assignedTo: string | null) {
    const previousAnnotations = annotationRows;
    setAnnotationRows((current) =>
      current.map((annotation) =>
        annotation.id === annotationId ? { ...annotation, assignedTo } : annotation
      )
    );
    try {
      const existing = annotationRows.find((annotation) => annotation.id === annotationId);
      const updated = await assignAnnotation(annotationId, assignedTo, existing?.revision);
      setAnnotationRows((current) =>
        current.map((annotation) => (annotation.id === annotationId ? updated : annotation))
      );
      await refreshAnnotationHistory(updated.datasetId, updated.episodeIndex);
      await refreshReviewQueue(updated.datasetId);
    } catch (error) {
      setAnnotationRows(previousAnnotations);
      await handleAnnotationMutationError(error, selectedEpisode.datasetId, selectedEpisode.episodeIndex);
      throw error;
    }
  }

  async function handleDeleteSegment(annotationId: string) {
    const previousAnnotations = annotationRows;
    setAnnotationRows((current) => current.filter((annotation) => annotation.id !== annotationId));
    try {
      const existing = previousAnnotations.find((annotation) => annotation.id === annotationId);
      await deleteAnnotation(annotationId, existing?.revision);
      await refreshAnnotationHistory(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
      await refreshReviewQueue(selectedEpisode.datasetId);
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
      await refreshAnnotationHistory(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
      await refreshReviewQueue(selectedEpisode.datasetId);
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
    format: ExportFormat = "lance",
    scope: "dataset" | "episode" | "split" = "dataset",
    options?: SkillExportOptions,
  ) {
    const split = selectedEpisode.split || null;
    const splits = scope === "split" && split ? [split] : [];
    const episodeIndices = scope === "episode" ? [selectedEpisode.episodeIndex] : [];
    const job = await createExportJob(
      selectedEpisode.datasetId,
      episodeIndices,
      format,
      splits,
      undefined,
      options ?? {
        clipLabelType: SKILL_LABEL_TYPE,
        acceptedClipsOnly: true,
        materializeSkillClips: format === "lance",
        jitterOffsets: [0],
        copiesPerClip: 1
      },
    );
    setExportJob(job);
    if (TERMINAL_JOB_STATUSES.has(job.status) && job.createdExportId) {
      const record = await fetchExport(job.createdExportId);
      setExportRecord(record);
      void refreshPastExports(record.datasetId);
    }
  }

  async function handleUploadExportToHub(
    exportId: string,
    repoId?: string,
  ): Promise<ExportHubUploadResult> {
    const result = await uploadExportToHub(exportId, repoId);
    const record = await fetchExport(exportId);
    setExportRecord(record);
    void refreshPastExports(record.datasetId);
    return result;
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
    await refreshAnnotationHistory(selectedEpisode.datasetId, selectedEpisode.episodeIndex);
    await refreshReviewQueue(selectedEpisode.datasetId);
  }

  return {
    annotationHistoryRows,
    annotationRows,
    dataStatus,
    episodeListStatus,
    episodeMetadataFilters,
    episodeNextOffset,
    episodeRows,
    episodeSearchText,
    episodeTotal,
    exportJob,
    exportRecord,
    pastExports,
    filterPresets,
    frameBrowserLimit,
    frameBrowserStart,
    framePage,
    frameRows,
    frameRowsStatus,
    rerunJob,
    rerunSession,
    rerunViewerUrl,
    reviewQueueRows,
    reviewerUserId,
    mutationNotice,
    searchResults,
    selectedEpisode,
    selectedEpisodeIndex,
    selectedFrameIndex,
    selectedFrameRecord,
    selectedFrameStatus,
    selectedSummary,
    selectedDatasetId,
    selectedDatasetHealth,
    summaries,
    vlmJob,
    vlmResponses,
    handleCreateExport,
    handleEpisodeMetadataFiltersChange,
    handleEpisodeSearchTextChange,
    handleLoadMoreEpisodes,
    handleUploadExportToHub,
    handleAssignAnnotation,
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
    handleSelectDataset,
    handleSelectEpisode,
    handleSelectFrame,
    handleDismissMutationNotice: () => setMutationNotice(null),
    handleSemanticSearch,
    handleSetEpisodeDisposition,
    handleSplitSegment,
    handleUpdateFrameBadFlag,
    handleSetFrameBrowserLimit,
    handleSetFrameBrowserStart,
    handleUpdateSelectedFrameLabel,
    handleUpdateSelectedFrameBadFlag,
    handleUpdateReviewStatus,
    handleUpdateSegment
  };
}
