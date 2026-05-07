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
        return (
          <button
            key={skill.id}
            type="button"
            className={`skill-chip${isActive ? " active" : ""}`}
            onClick={() => onSelect(skill.id)}
            title={`${skill.label} (key ${skill.id})`}
            style={{ ["--skill-color" as string]: skill.color }}
          >
            <span className="skill-chip-key">{skill.id}</span>
            <span className="skill-chip-label">{skill.label}</span>
          </button>
        );
      })}
    </div>
  );
}
