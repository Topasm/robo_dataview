"use client";

import { useEffect } from "react";

import { HUMANOID_SKILLS, SKILL_LABEL_TYPE, skillById } from "@/lib/skill-vocabulary";
import type { useStudioData } from "@/lib/use-studio-data";

type StudioData = ReturnType<typeof useStudioData>;

type UseAnnotateShortcutsOptions = {
  enabled: boolean;
  enableBadFrameShortcuts: boolean;
  studio: StudioData;
  clipStart: number | null;
  clipEnd: number | null;
  setClipStart: (frame: number | null) => void;
  setClipEnd: (frame: number | null) => void;
  selectedClipId: string | null;
  setSelectedClipId: (id: string | null) => void;
  setSelectedSkillId: (id: number) => void;
  setSelectedSkillName?: (name: string) => void;
};

export function useAnnotateShortcuts({
  enabled,
  enableBadFrameShortcuts,
  studio,
  clipStart,
  clipEnd,
  setClipStart,
  setClipEnd,
  selectedClipId,
  setSelectedClipId,
  setSelectedSkillId,
  setSelectedSkillName
}: UseAnnotateShortcutsOptions): void {
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
      const fps = studio.selectedEpisode?.fps > 0 ? studio.selectedEpisode.fps : 20;

      // --- Frame stepping ---
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

      // --- In/out markers ---
      const key = event.key.toLowerCase();
      if (key === "i") {
        event.preventDefault();
        setClipStart(frame);
        return;
      }
      if (key === "o") {
        event.preventDefault();
        setClipEnd(frame);
        return;
      }

      // --- Cancel draft ---
      if (event.key === "0") {
        event.preventDefault();
        setClipStart(null);
        setClipEnd(null);
        return;
      }

      // --- 1-9: select skill id; reassign+accept selected pending clip OR create from I/O ---
      if (event.key >= "1" && event.key <= "9") {
        event.preventDefault();
        const skillId = Number(event.key);
        if (skillId >= HUMANOID_SKILLS.length) {
          return;
        }
        setSelectedSkillId(skillId);
        const skill = skillById(skillId);
        if (!skill) {
          return;
        }
        setSelectedSkillName?.(skill.name);

        // Path A: a pending skill-clip is selected → reassign skill + accept
        const selected = selectedClipId
          ? studio.annotationRows.find((row) => row.id === selectedClipId)
          : null;
        if (
          selected &&
          selected.labelType === SKILL_LABEL_TYPE &&
          selected.reviewStatus === "pending"
        ) {
          void studio.handleUpdateSegment(selected.id, {
            labelType: SKILL_LABEL_TYPE,
            labelValue: skill.name,
            startFrame: selected.startFrame,
            endFrame: selected.endFrame,
            reviewStatus: "accepted",
            metadata: { ...selected.metadata, skillId: skill.id }
          });
          setSelectedClipId(null);
          return;
        }

        // Path B: both I/O markers set → create new accepted clip
        if (clipStart !== null && clipEnd !== null) {
          const start = Math.min(clipStart, clipEnd);
          const end = Math.max(clipStart, clipEnd);
          void studio.handleCreateSegment({
            labelType: SKILL_LABEL_TYPE,
            labelValue: skill.name,
            startFrame: start,
            endFrame: end,
            reviewStatus: "accepted",
            metadata: { skillId: skill.id, qualityScore: null, successLabel: null }
          });
          setClipStart(null);
          setClipEnd(null);
        }
        return;
      }

      // --- Delete selected clip ---
      if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        if (selectedClipId !== null) {
          void studio.handleDeleteSegment(selectedClipId);
          setSelectedClipId(null);
        }
        return;
      }

      // --- Opt-in: bad frame / bad range ---
      if (!enableBadFrameShortcuts) {
        return;
      }
      if (key === "m") {
        event.preventDefault();
        void studio.handleUpdateSelectedFrameBadFlag(
          !(studio.selectedFrameRecord?.isBadFrame ?? false)
        );
        return;
      }
      if (key === "b") {
        event.preventDefault();
        const radius = Math.max(1, Math.round(fps / 2));
        void studio.handleCreateSegment({
          labelType: "bad_range",
          labelValue: "bad_range",
          startFrame: Math.max(0, frame - radius),
          endFrame: Math.min(lastFrame, frame + radius)
        });
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    enabled,
    enableBadFrameShortcuts,
    studio,
    clipStart,
    clipEnd,
    setClipStart,
    setClipEnd,
    selectedClipId,
    setSelectedClipId,
    setSelectedSkillId
  ]);
}
