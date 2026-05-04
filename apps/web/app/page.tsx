"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot, Database, Download, Settings } from "lucide-react";

import { AnnotationEditor } from "@/features/annotation-editor/annotation-editor";
import { DatasetBrowser } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { TimelinePanel } from "@/features/episode-viewer/timeline-panel";
import { ExportStrip } from "@/features/export-manager/export-strip";
import { RerunPanel } from "@/features/rerun-viewer/rerun-panel";
import { SearchFilterBar } from "@/features/search-filter/search-filter-bar";
import { fetchDatasetSummaries, fetchEpisodes, openDataset } from "@/lib/api";
import { annotations, datasetSummary, episodes } from "@/lib/sample-data";
import type { DatasetSummary, Episode } from "@/lib/types";

export default function Home() {
  const [summaries, setSummaries] = useState<DatasetSummary[]>([datasetSummary]);
  const [episodeRows, setEpisodeRows] = useState<Episode[]>(episodes);
  const [selectedDatasetId, setSelectedDatasetId] = useState(datasetSummary.datasetId);
  const [selectedEpisodeIndex, setSelectedEpisodeIndex] = useState(episodes[0].episodeIndex);
  const [dataStatus, setDataStatus] = useState<"loading" | "api" | "sample">("loading");
  const selectedSummary =
    summaries.find((summary) => summary.datasetId === selectedDatasetId) ?? summaries[0] ?? datasetSummary;
  const rerunViewerUrl = process.env.NEXT_PUBLIC_RERUN_IFRAME_URL ?? null;
  const selectedEpisode = useMemo(
    () =>
      episodeRows.find((episode) => episode.episodeIndex === selectedEpisodeIndex) ??
      episodeRows[0] ??
      episodes[0],
    [episodeRows, selectedEpisodeIndex]
  );

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
        setDataStatus("api");
      } catch {
        if (!isMounted) {
          return;
        }
        setSummaries([datasetSummary]);
        setSelectedDatasetId(datasetSummary.datasetId);
        setEpisodeRows(episodes);
        setSelectedEpisodeIndex(episodes[0].episodeIndex);
        setDataStatus("sample");
      }
    }

    loadInitialData();
    return () => {
      isMounted = false;
    };
  }, []);

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
    setDataStatus("api");
  }

  return (
    <div className="studio-shell">
      <header className="top-bar">
        <div className="brand">
          <Database size={18} />
          <span>Robot Data Studio</span>
        </div>
        <nav className="top-nav">
          <button className="nav-button active" type="button">
            Dataset
          </button>
          <button className="nav-button" type="button">
            Task
          </button>
          <button className="nav-button" type="button">
            Search
          </button>
          <button className="nav-button" type="button">
            <Bot size={15} />
            VLM Jobs
          </button>
          <button className="nav-button" type="button">
            <Download size={15} />
            Export
          </button>
        </nav>
        <button className="icon-button" title="Settings" type="button">
          <Settings size={17} />
        </button>
      </header>

      <div className={`data-source-banner data-source-${dataStatus}`}>
        {dataStatus === "loading"
          ? "Loading API datasets"
          : dataStatus === "api"
            ? `API dataset: ${selectedSummary.name}`
            : "Sample data fallback"}
      </div>

      <div className="workspace">
        <DatasetBrowser onOpenDataset={handleOpenDataset} summary={selectedSummary} />
        <div className="center-column">
          <SearchFilterBar />
          <div className="content-split">
            <div className="viewer-column">
              <EpisodeViewer episode={selectedEpisode} />
              <TimelinePanel annotations={annotations} frameCount={selectedEpisode.length} />
              <RerunPanel viewerUrl={rerunViewerUrl} />
            </div>
            <AnnotationEditor annotations={annotations} episode={selectedEpisode} />
          </div>
          <ExportStrip />
        </div>
        <EpisodeList
          episodes={episodeRows}
          onSelectEpisode={setSelectedEpisodeIndex}
          selectedEpisodeIndex={selectedEpisodeIndex}
        />
      </div>
    </div>
  );
}
