"use client";

import { useCallback, useEffect, useState } from "react";

import { SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type { Episode, SegmentAnnotation } from "@/lib/types";

export type CameraLayout = "focus" | "grid";
export type IconRailPanel = "episodes" | "search" | "rerun" | null;

export type LastEpisodeClip = {
  skillName: string;
  skillId: number;
  startFrame: number;
  endFrame: number;
};

export type LastEpisodeBoundaries = {
  datasetId: string;
  episodeIndex: number;
  frameCount: number;
  clips: LastEpisodeClip[];
  capturedAt: string;
};

const STORAGE_KEY_SIGNAL_PRESET = "robot-data-studio:annotation:signal-preset";
const STORAGE_KEY_CAMERA_LAYOUT = "robot-data-studio:annotation:camera-layout";
const STORAGE_KEY_BAD_FRAME_SHORTCUTS = "robot-data-studio:annotation:enable-bad-frame-shortcuts";
const STORAGE_KEY_LAST_EPISODE = "robot-data-studio:annotation:last-episode-boundaries";
const STORAGE_KEY_DISMISSED_COACH = "robot-data-studio:annotation:dismissed-coach-episodes";

function coachKey(datasetId: string, episodeIndex: number): string {
  return `${datasetId}::${episodeIndex}`;
}

function readStorage(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore quota / disabled storage
  }
}

export function useAnnotationEditor() {
  const [cameraLayout, setCameraLayoutState] = useState<CameraLayout>("grid");
  const [activeSignalPreset, setActiveSignalPresetState] = useState<string>("overview");
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);
  const [railPanel, setRailPanel] = useState<IconRailPanel>(null);
  const [railPinned, setRailPinned] = useState(false);
  const [enableBadFrameShortcuts, setEnableBadFrameShortcutsState] = useState(false);
  const [lastEpisodeBoundaries, setLastEpisodeBoundariesState] =
    useState<LastEpisodeBoundaries | null>(null);
  const [dismissedCoachKeys, setDismissedCoachKeysState] = useState<Set<string>>(
    () => new Set()
  );

  useEffect(() => {
    const storedLayout = readStorage(STORAGE_KEY_CAMERA_LAYOUT);
    if (storedLayout === "focus" || storedLayout === "grid") {
      setCameraLayoutState(storedLayout);
    }
    const storedPreset = readStorage(STORAGE_KEY_SIGNAL_PRESET);
    if (storedPreset) {
      setActiveSignalPresetState(storedPreset);
    }
    const storedBadFrame = readStorage(STORAGE_KEY_BAD_FRAME_SHORTCUTS);
    if (storedBadFrame === "1") {
      setEnableBadFrameShortcutsState(true);
    }
    const storedLastEpisode = readStorage(STORAGE_KEY_LAST_EPISODE);
    if (storedLastEpisode) {
      try {
        const parsed = JSON.parse(storedLastEpisode) as LastEpisodeBoundaries;
        if (parsed && Array.isArray(parsed.clips) && parsed.clips.length > 0) {
          setLastEpisodeBoundariesState(parsed);
        }
      } catch {
        // ignore corrupted entry
      }
    }
    const storedCoachDismiss = readStorage(STORAGE_KEY_DISMISSED_COACH);
    if (storedCoachDismiss) {
      try {
        const arr = JSON.parse(storedCoachDismiss);
        if (Array.isArray(arr)) {
          setDismissedCoachKeysState(new Set(arr.filter((v): v is string => typeof v === "string")));
        }
      } catch {
        // ignore corrupted entry
      }
    }
  }, []);

  const setCameraLayout = useCallback((next: CameraLayout) => {
    setCameraLayoutState(next);
    writeStorage(STORAGE_KEY_CAMERA_LAYOUT, next);
  }, []);

  const setActiveSignalPreset = useCallback((next: string) => {
    setActiveSignalPresetState(next);
    writeStorage(STORAGE_KEY_SIGNAL_PRESET, next);
  }, []);

  const toggleCheatsheet = useCallback(() => {
    setCheatsheetOpen((current) => !current);
  }, []);

  const closeCheatsheet = useCallback(() => {
    setCheatsheetOpen(false);
  }, []);

  const toggleRailPanel = useCallback((next: IconRailPanel) => {
    setRailPanel((current) => (current === next ? null : next));
  }, []);

  const closeRailPanel = useCallback(() => {
    if (!railPinned) {
      setRailPanel(null);
    }
  }, [railPinned]);

  const togglePin = useCallback(() => {
    setRailPinned((current) => !current);
  }, []);

  const setEnableBadFrameShortcuts = useCallback((next: boolean) => {
    setEnableBadFrameShortcutsState(next);
    writeStorage(STORAGE_KEY_BAD_FRAME_SHORTCUTS, next ? "1" : "0");
  }, []);

  const captureLastEpisode = useCallback(
    (episode: Pick<Episode, "datasetId" | "episodeIndex" | "length">, annotations: SegmentAnnotation[]) => {
      const skillClips: LastEpisodeClip[] = annotations
        .filter(
          (row) =>
            row.datasetId === episode.datasetId &&
            row.episodeIndex === episode.episodeIndex &&
            row.labelType === SKILL_LABEL_TYPE &&
            row.reviewStatus === "accepted"
        )
        .map((row) => {
          const skillIdRaw = row.metadata?.skillId;
          const skillId = typeof skillIdRaw === "number" ? skillIdRaw : 0;
          return {
            skillName: row.labelValue,
            skillId,
            startFrame: row.startFrame,
            endFrame: row.endFrame
          };
        })
        .sort((a, b) => a.startFrame - b.startFrame);
      if (skillClips.length === 0) {
        return;
      }
      const next: LastEpisodeBoundaries = {
        datasetId: episode.datasetId,
        episodeIndex: episode.episodeIndex,
        frameCount: Math.max(1, episode.length),
        clips: skillClips,
        capturedAt: new Date().toISOString()
      };
      setLastEpisodeBoundariesState(next);
      writeStorage(STORAGE_KEY_LAST_EPISODE, JSON.stringify(next));
    },
    []
  );

  const clearLastEpisode = useCallback(() => {
    setLastEpisodeBoundariesState(null);
    writeStorage(STORAGE_KEY_LAST_EPISODE, "");
  }, []);

  const isCoachDismissed = useCallback(
    (datasetId: string, episodeIndex: number) =>
      dismissedCoachKeys.has(coachKey(datasetId, episodeIndex)),
    [dismissedCoachKeys]
  );

  const dismissCoach = useCallback((datasetId: string, episodeIndex: number) => {
    setDismissedCoachKeysState((current) => {
      const key = coachKey(datasetId, episodeIndex);
      if (current.has(key)) {
        return current;
      }
      const next = new Set(current);
      next.add(key);
      writeStorage(STORAGE_KEY_DISMISSED_COACH, JSON.stringify(Array.from(next)));
      return next;
    });
  }, []);

  return {
    cameraLayout,
    setCameraLayout,
    activeSignalPreset,
    setActiveSignalPreset,
    cheatsheetOpen,
    toggleCheatsheet,
    closeCheatsheet,
    railPanel,
    setRailPanel,
    toggleRailPanel,
    closeRailPanel,
    railPinned,
    togglePin,
    enableBadFrameShortcuts,
    setEnableBadFrameShortcuts,
    lastEpisodeBoundaries,
    captureLastEpisode,
    clearLastEpisode,
    isCoachDismissed,
    dismissCoach
  };
}
