"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, Download, Settings } from "lucide-react";

import { DirtyChip } from "@/components/dirty-chip";
import { AnnotationMode } from "@/features/annotation-mode/annotation-mode";
import { BrowseMode } from "@/features/browse-mode/browse-mode";
import { ExportModal } from "@/features/export-manager/export-modal";
import { HUMANOID_SKILLS } from "@/lib/skill-vocabulary";
import { useStudioData } from "@/lib/use-studio-data";

type ActiveTab = "browse" | "annotate";

export default function Home() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("browse");
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  const [clipStart, setClipStart] = useState<number | null>(null);
  const [clipEnd, setClipEnd] = useState<number | null>(null);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [selectedSkillId, setSelectedSkillId] = useState<number>(0);
  // Authoritative selection — labelValue stored on annotations. Tracks
  // both canonical 0–9 and custom skills added through the SkillHotBar.
  // selectedSkillId stays around for the keyboard-shortcut machinery
  // (1–9 picks the canonical skill at that slot).
  const [selectedSkillName, setSelectedSkillName] = useState<string>(
    HUMANOID_SKILLS[0].name
  );
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);

  const studio = useStudioData();
  const {
    dataStatus,
    episodeRows,
    handleDismissMutationNotice,
    handleSelectEpisode,
    mutationNotice,
    selectedEpisode,
    selectedSummary
  } = studio;

  const dirtyEpisodeCount = useMemo(
    () => episodeRows.filter((episode) => (episode.dirtyAnnotationCount ?? 0) > 0).length,
    [episodeRows]
  );

  const handleJumpToFirstDirty = useCallback(() => {
    const firstDirty = episodeRows.find(
      (episode) => (episode.dirtyAnnotationCount ?? 0) > 0
    );
    if (firstDirty) {
      handleSelectEpisode(firstDirty.episodeIndex);
    }
  }, [episodeRows, handleSelectEpisode]);

  const toggleSignals = useCallback(() => setShowSignals((current) => !current), []);
  const openCheatsheet = useCallback(() => setCheatsheetOpen(true), []);
  const closeCheatsheet = useCallback(() => setCheatsheetOpen(false), []);

  useEffect(() => {
    setClipStart(null);
    setClipEnd(null);
    setSelectedClipId(null);
  }, [selectedEpisode.datasetId, selectedEpisode.episodeIndex]);

  // Cross-tab globals only (`?` cheatsheet, Esc). Tab-specific keymaps live in
  // useBrowseShortcuts / useAnnotateShortcuts inside their mode components.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTyping) {
        return;
      }
      if (event.key === "?" || (event.shiftKey && event.key === "/")) {
        event.preventDefault();
        setCheatsheetOpen((current) => !current);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        if (cheatsheetOpen) {
          setCheatsheetOpen(false);
        } else if (exportModalOpen) {
          setExportModalOpen(false);
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cheatsheetOpen, exportModalOpen]);

  return (
    <div className="studio-shell">
      <header className="top-bar">
        <div className="brand">
          <Database size={18} />
          <span>Robot Data Studio</span>
        </div>
        <nav className="top-nav" aria-label="Workspace mode">
          <button
            className={`nav-button ${activeTab === "browse" ? "active" : ""}`}
            onClick={() => setActiveTab("browse")}
            type="button"
            aria-label="Switch to Browse mode"
            aria-pressed={activeTab === "browse"}
          >
            Browse
          </button>
          <button
            className={`nav-button ${activeTab === "annotate" ? "active" : ""}`}
            onClick={() => setActiveTab("annotate")}
            type="button"
            aria-label="Switch to Annotate mode"
            aria-pressed={activeTab === "annotate"}
          >
            Annotate
          </button>
        </nav>
        <div className="top-bar-actions">
          <DirtyChip count={dirtyEpisodeCount} onJumpToFirst={handleJumpToFirstDirty} />
          <button
            className={`btn btn--sm top-apply-button${exportModalOpen ? " active" : ""}`}
            onClick={() => setExportModalOpen((current) => !current)}
            title="Apply curated Browse/Annotate edits, then upload the export to Hugging Face"
            aria-label="Open apply and upload panel"
            aria-pressed={exportModalOpen}
            type="button"
          >
            <Download size={14} />
            <span>Apply / Upload</span>
          </button>
          <button className="icon-button" title="Advanced settings" aria-label="Advanced settings" type="button">
            <Settings size={17} />
          </button>
        </div>
      </header>

      <div className={`data-source-banner data-source-${dataStatus}`}>
        {dataStatus === "loading"
          ? "Loading API datasets"
          : dataStatus === "api"
            ? `API dataset: ${selectedSummary.name}`
            : "Sample data fallback"}
      </div>
      {mutationNotice ? (
        <div className="data-source-banner data-source-sample">
          <span>{mutationNotice}</span>
          <button className="text-button compact-text-button" onClick={handleDismissMutationNotice} type="button">
            Dismiss
          </button>
        </div>
      ) : null}

      {activeTab === "browse" ? (
        <BrowseMode
          studio={studio}
          onSwitchToAnnotate={() => setActiveTab("annotate")}
          exportModalOpen={exportModalOpen}
          onToggleExport={() => setExportModalOpen((current) => !current)}
        />
      ) : null}
      {activeTab === "annotate" ? (
        <AnnotationMode
          studio={studio}
          showSignals={showSignals}
          onToggleSignals={toggleSignals}
          clipStart={clipStart}
          clipEnd={clipEnd}
          onSetClipStart={setClipStart}
          onSetClipEnd={setClipEnd}
          selectedClipId={selectedClipId}
          onSetSelectedClipId={setSelectedClipId}
          selectedSkillId={selectedSkillId}
          onSetSelectedSkillId={setSelectedSkillId}
          selectedSkillName={selectedSkillName}
          onSetSelectedSkillName={setSelectedSkillName}
          cheatsheetOpen={cheatsheetOpen}
          onCloseCheatsheet={closeCheatsheet}
          onOpenCheatsheet={openCheatsheet}
          exportModalOpen={exportModalOpen}
          onToggleExport={() => setExportModalOpen((current) => !current)}
        />
      ) : null}
      <ExportModal
        open={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        studio={studio}
      />
    </div>
  );
}
