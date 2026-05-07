"use client";

import { useEffect, useState } from "react";
import { Check, Flag, Scissors, Trash2, X } from "lucide-react";

type EpisodeActionBarProps = {
  episodeIndex: number;
  episodeCaption?: string | null;
  onMarkDisposition:
    | ((kind: "kept" | "deleted" | "flagged", reason: string | null) => void)
    | null;
  onSwitchToAnnotate: () => void;
};

export function EpisodeActionBar({
  episodeIndex,
  episodeCaption,
  onMarkDisposition,
  onSwitchToAnnotate
}: EpisodeActionBarProps) {
  const dispositionDisabled = onMarkDisposition === null;
  const dispositionTitle = dispositionDisabled
    ? "Episode disposition wires up in Sprint 2"
    : undefined;
  const [flagOpen, setFlagOpen] = useState(false);
  const [flagReason, setFlagReason] = useState("");

  useEffect(() => {
    if (!flagOpen) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setFlagOpen(false);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [flagOpen]);

  function handleKeep() {
    if (onMarkDisposition) {
      onMarkDisposition("kept", null);
    }
  }

  function handleDelete() {
    if (onMarkDisposition) {
      onMarkDisposition("deleted", null);
    }
  }

  function handleOpenFlag() {
    if (!onMarkDisposition) {
      return;
    }
    setFlagReason("");
    setFlagOpen(true);
  }

  function handleSubmitFlag() {
    if (!onMarkDisposition) {
      return;
    }
    const trimmed = flagReason.trim();
    onMarkDisposition("flagged", trimmed.length > 0 ? trimmed : null);
    setFlagOpen(false);
    setFlagReason("");
  }

  return (
    <div className="episode-action-bar">
      <div className="episode-action-meta">
        <span className="episode-action-title">Episode #{episodeIndex}</span>
        {episodeCaption ? (
          <span className="muted episode-action-caption">{episodeCaption}</span>
        ) : null}
      </div>
      <div className="episode-action-group">
        <button
          className="btn"
          disabled={dispositionDisabled}
          onClick={handleKeep}
          title={dispositionTitle ?? "Mark this episode as kept"}
          type="button"
        >
          <Check size={16} />
          <span>Keep</span>
        </button>
        <button
          className="btn btn--danger"
          disabled={dispositionDisabled}
          onClick={handleDelete}
          title={dispositionTitle ?? "Mark this episode as deleted"}
          type="button"
        >
          <Trash2 size={16} />
          <span>Delete</span>
        </button>
        <button
          className="btn btn--warning"
          disabled={dispositionDisabled}
          onClick={handleOpenFlag}
          title={dispositionTitle ?? "Flag this episode for follow-up"}
          type="button"
        >
          <Flag size={16} />
          <span>Flag</span>
        </button>
      </div>
      <div className="episode-action-spacer" />
      <button
        className="btn btn--primary"
        onClick={onSwitchToAnnotate}
        title="Open this episode in the Annotate workspace"
        type="button"
      >
        <Scissors size={16} />
        <span>Annotate this episode &rarr;</span>
      </button>

      {flagOpen ? (
        <div
          className="modal-overlay"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setFlagOpen(false);
            }
          }}
        >
          <div className="modal-panel" role="dialog" aria-label="Flag episode">
            <header className="modal-header">
              <div className="modal-header-title">
                <Flag size={18} />
                <h2>Flag episode #{episodeIndex}</h2>
              </div>
              <button
                type="button"
                className="btn btn--ghost btn--icon"
                onClick={() => setFlagOpen(false)}
                aria-label="Close flag dialog"
              >
                <X size={16} />
              </button>
            </header>
            <div className="modal-body">
              <form
                className="flag-reason-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleSubmitFlag();
                }}
              >
                <label htmlFor="flag-reason-textarea">
                  Reason <span className="muted">(optional)</span>
                </label>
                <textarea
                  id="flag-reason-textarea"
                  autoFocus
                  rows={4}
                  value={flagReason}
                  onChange={(event) => setFlagReason(event.target.value)}
                  placeholder="Describe why this episode needs follow-up"
                />
              </form>
            </div>
            <footer className="modal-footer">
              <button
                type="button"
                className="btn"
                onClick={() => setFlagOpen(false)}
              >
                Cancel
              </button>
              <button type="button" className="btn btn--primary" onClick={handleSubmitFlag}>
                <Flag size={16} />
                <span>Flag with reason</span>
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
