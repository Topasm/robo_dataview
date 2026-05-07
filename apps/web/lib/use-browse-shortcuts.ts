"use client";

import { useEffect } from "react";

import type { useStudioData } from "@/lib/use-studio-data";

type StudioData = ReturnType<typeof useStudioData>;

export type EpisodeDispositionKind = "kept" | "deleted" | "flagged";

type UseBrowseShortcutsOptions = {
  enabled: boolean;
  studio: StudioData;
  onSwitchToAnnotate: () => void;
  onMarkDisposition:
    | ((kind: EpisodeDispositionKind, reason: string | null) => void)
    | null;
};

export function useBrowseShortcuts({
  enabled,
  studio,
  onSwitchToAnnotate,
  onMarkDisposition
}: UseBrowseShortcutsOptions): void {
  useEffect(() => {
    if (!enabled) {
      return;
    }
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
      const lastFrame = Math.max(0, (studio.selectedEpisode?.length ?? 1) - 1);
      const frame = studio.selectedFrameIndex;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        studio.handleSelectFrame(Math.max(0, frame - (event.shiftKey ? 10 : 1)));
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        studio.handleSelectFrame(Math.min(lastFrame, frame + (event.shiftKey ? 10 : 1)));
        return;
      }
      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        const rows = studio.episodeRows;
        if (rows.length === 0) {
          return;
        }
        const currentIndex = rows.findIndex(
          (ep) => ep.episodeIndex === studio.selectedEpisodeIndex
        );
        const direction = event.key === "ArrowUp" ? -1 : 1;
        const nextIndex =
          currentIndex < 0
            ? 0
            : Math.max(0, Math.min(rows.length - 1, currentIndex + direction));
        const next = rows[nextIndex];
        if (next) {
          studio.handleSelectEpisode(next.episodeIndex);
        }
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        onSwitchToAnnotate();
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "k" || key === "x" || key === "f") {
        if (!onMarkDisposition) {
          return;
        }
        event.preventDefault();
        const kind: EpisodeDispositionKind =
          key === "k" ? "kept" : key === "x" ? "deleted" : "flagged";
        onMarkDisposition(kind, null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, studio, onSwitchToAnnotate, onMarkDisposition]);
}
