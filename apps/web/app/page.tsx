"use client";

import { useMemo, useState } from "react";
import { Bot, Database, Download, Settings } from "lucide-react";

import { AnnotationEditor } from "@/features/annotation-editor/annotation-editor";
import { DatasetBrowser } from "@/features/dataset-browser/dataset-browser";
import { EpisodeList } from "@/features/dataset-browser/episode-list";
import { EpisodeViewer } from "@/features/episode-viewer/episode-viewer";
import { TimelinePanel } from "@/features/episode-viewer/timeline-panel";
import { ExportStrip } from "@/features/export-manager/export-strip";
import { RerunPanel } from "@/features/rerun-viewer/rerun-panel";
import { SearchFilterBar } from "@/features/search-filter/search-filter-bar";
import { annotations, datasetSummary, episodes } from "@/lib/sample-data";

export default function Home() {
  const [selectedEpisodeIndex, setSelectedEpisodeIndex] = useState(episodes[0].episodeIndex);
  const selectedEpisode = useMemo(
    () => episodes.find((episode) => episode.episodeIndex === selectedEpisodeIndex) ?? episodes[0],
    [selectedEpisodeIndex]
  );

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

      <div className="workspace">
        <DatasetBrowser summary={datasetSummary} />
        <div className="center-column">
          <SearchFilterBar />
          <div className="content-split">
            <div className="viewer-column">
              <EpisodeViewer episode={selectedEpisode} />
              <TimelinePanel annotations={annotations} frameCount={selectedEpisode.length} />
              <RerunPanel />
            </div>
            <AnnotationEditor annotations={annotations} episode={selectedEpisode} />
          </div>
          <ExportStrip />
        </div>
        <EpisodeList
          episodes={episodes}
          onSelectEpisode={setSelectedEpisodeIndex}
          selectedEpisodeIndex={selectedEpisodeIndex}
        />
      </div>
    </div>
  );
}
