"use client";

import { HUMANOID_SKILLS } from "@/lib/skill-vocabulary";

type SkillHotBarProps = {
  selectedSkillId: number;
  onSelect: (id: number) => void;
};

export function SkillHotBar({ selectedSkillId, onSelect }: SkillHotBarProps) {
  return (
    <div className="skill-hot-bar" role="toolbar" aria-label="Skill picker">
      {HUMANOID_SKILLS.map((skill) => {
        const isActive = skill.id === selectedSkillId;
        // Skill 0 (approach) loses its keyboard shortcut — digit "0" cancels the
        // current draft instead. Show a click-only marker on its chip so users
        // don't expect a 0 keystroke to pick approach.
        const clickOnly = skill.id === 0;
        return (
          <button
            key={skill.id}
            type="button"
            className={`skill-chip${isActive ? " active" : ""}${clickOnly ? " click-only" : ""}`}
            onClick={() => onSelect(skill.id)}
            title={
              clickOnly
                ? `${skill.label} — click only (no keyboard shortcut)`
                : `${skill.label} (key ${skill.id})`
            }
            style={{ ["--skill-color" as string]: skill.color }}
          >
            <span className="skill-chip-key" aria-hidden={clickOnly}>
              {clickOnly ? "·" : skill.id}
            </span>
            <span className="skill-chip-label">{skill.label}</span>
          </button>
        );
      })}
    </div>
  );
}
