"use client";

import { HUMANOID_SKILLS, SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type { SegmentAnnotation } from "@/lib/types";

type StatusHudProps = {
  frameIndex: number;
  frameCount: number;
  fps: number;
  selectedSkillId: number;
  clipStart: number | null;
  clipEnd: number | null;
  annotations: SegmentAnnotation[];
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) {
    return "0:00.00";
  }
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  const wholeSeconds = Math.floor(remainder);
  const hundredths = Math.floor((remainder - wholeSeconds) * 100);
  return `${minutes}:${wholeSeconds.toString().padStart(2, "0")}.${hundredths
    .toString()
    .padStart(2, "0")}`;
}

export function StatusHud({
  frameIndex,
  frameCount,
  fps,
  selectedSkillId,
  clipStart,
  clipEnd,
  annotations
}: StatusHudProps) {
  const lastFrame = Math.max(0, frameCount - 1);
  const safeFps = fps > 0 ? fps : 20;
  const skill = HUMANOID_SKILLS.find((s) => s.id === selectedSkillId);
  const acceptedSkillClips = annotations.filter(
    (row) => row.labelType === SKILL_LABEL_TYPE && row.reviewStatus === "accepted"
  ).length;
  const totalSkillClips = annotations.filter((row) => row.labelType === SKILL_LABEL_TYPE).length;

  const draftActive = clipStart !== null || clipEnd !== null;
  const draftLabel = (() => {
    if (clipStart === null && clipEnd === null) {
      return "—";
    }
    const inLabel = clipStart === null ? "—" : `f${clipStart}`;
    const outLabel = clipEnd === null ? "—" : `f${clipEnd}`;
    return `${inLabel} → ${outLabel}`;
  })();

  return (
    <div className="status-hud">
      <span className="status-hud-cell">
        <span className="status-hud-key">Frame</span>
        <span className="status-hud-value mono">
          {frameIndex.toString().padStart(String(lastFrame).length, "0")}/{lastFrame}
        </span>
      </span>
      <span className="status-hud-cell">
        <span className="status-hud-key">Time</span>
        <span className="status-hud-value mono">{formatTime(frameIndex / safeFps)}</span>
      </span>
      <span className="status-hud-cell">
        <span className="status-hud-key">FPS</span>
        <span className="status-hud-value mono">{safeFps}</span>
      </span>
      <span className="status-hud-cell">
        <span className="status-hud-key">Skill</span>
        {skill ? (
          <span
            className="status-hud-skill"
            style={{ ["--skill-color" as string]: skill.color }}
          >
            <span className="status-hud-skill-dot" />
            {skill.label}
            <span className="status-hud-skill-id mono">[{skill.id}]</span>
          </span>
        ) : (
          <span className="status-hud-value">—</span>
        )}
      </span>
      <span className={`status-hud-cell${draftActive ? " active" : ""}`}>
        <span className="status-hud-key">Draft</span>
        <span className="status-hud-value mono">{draftLabel}</span>
      </span>
      <span className="status-hud-cell">
        <span className="status-hud-key">Clips</span>
        <span className="status-hud-value mono">
          {acceptedSkillClips}/{totalSkillClips} accepted
        </span>
      </span>
    </div>
  );
}
