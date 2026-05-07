"use client";

import { useEffect } from "react";
import { Loader2, Sparkles, Wand2, X } from "lucide-react";

import type { useStudioData } from "@/lib/use-studio-data";

type StudioData = ReturnType<typeof useStudioData>;

type AutoLabelDialogProps = {
  open: boolean;
  onClose: () => void;
  studio: StudioData;
};

export function AutoLabelDialog({ open, onClose, studio }: AutoLabelDialogProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const pending = studio.annotationRows.filter(
    (row) => row.source === "vlm" && row.reviewStatus === "pending"
  ).length;

  const jobStatus = studio.vlmJob?.status ?? null;
  const isRunning = jobStatus === "queued" || jobStatus === "running";
  const isSucceeded = jobStatus === "succeeded";

  async function handleRun() {
    await studio.handleRunVlmLabel();
  }

  return (
    <div
      className="modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="modal-panel" role="dialog" aria-label="Auto Label this episode">
        <header className="modal-header">
          <div className="modal-header-title">
            <Sparkles size={18} />
            <h2>Auto Label this episode</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close auto label dialog"
          >
            <X size={16} />
          </button>
        </header>
        <div className="modal-body">
          <p>
            Run the VLM auto-labeler on this episode to generate skill boundary proposals. Each
            proposal lands in the timeline as a pending suggestion that you can accept, edit, or
            reject before exporting.
          </p>
          <dl className="auto-label-placeholder-stats">
            <div>
              <dt>Pending VLM proposals</dt>
              <dd>{pending}</dd>
            </div>
            <div>
              <dt>Episode</dt>
              <dd>{studio.selectedEpisode.episodeIndex}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>{studio.selectedSummary.name}</dd>
            </div>
          </dl>
          {isSucceeded ? (
            <p className="auto-label-success">
              Proposals ready &mdash; review them in the timeline below.
            </p>
          ) : null}
        </div>
        <footer className="modal-footer">
          <button
            type="button"
            className="primary-button"
            onClick={handleRun}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <Loader2 className="spin-icon" size={16} />
                <span>Running VLM auto-label&hellip;</span>
              </>
            ) : (
              <>
                <Wand2 size={16} />
                <span>Run VLM auto-label on this episode</span>
              </>
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}
