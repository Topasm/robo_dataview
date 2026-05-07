"use client";

import { useEffect } from "react";
import { Download, X } from "lucide-react";

import { ExportStrip } from "@/features/export-manager/export-strip";
import type { useStudioData } from "@/lib/use-studio-data";

type StudioData = ReturnType<typeof useStudioData>;

type ExportModalProps = {
  open: boolean;
  onClose: () => void;
  studio: StudioData;
};

export function ExportModal({ open, onClose, studio }: ExportModalProps) {
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

  return (
    <div
      className="modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="modal-panel export-modal-panel" role="dialog" aria-label="Apply to dataset">
        <header className="modal-header">
          <div className="modal-header-title">
            <Download size={18} />
            <h2>Apply to dataset</h2>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={onClose}
            aria-label="Close apply dialog"
          >
            <X size={16} />
          </button>
        </header>
        <div className="modal-body export-modal-body">
          <ExportStrip
            annotations={studio.annotationRows}
            episodeIndex={studio.selectedEpisode.episodeIndex}
            exportJob={studio.exportJob}
            exportRecord={studio.exportRecord}
            pastExports={studio.pastExports}
            onCreateExport={studio.handleCreateExport}
            split={studio.selectedEpisode.split}
          />
        </div>
      </div>
    </div>
  );
}
