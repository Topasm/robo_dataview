"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { SkillCombobox } from "@/components/skill-combobox";
import { removeCustomSkill, useCustomSkills } from "@/lib/custom-skills";
import { HUMANOID_SKILLS } from "@/lib/skill-vocabulary";

type SkillHotBarProps = {
  /** Current selection — labelValue (canonical name or custom). */
  selectedSkillName: string;
  /** Set when a canonical pill is clicked (kept in sync for the 0–9 hotkey). */
  onSelectId: (id: number) => void;
  /** Set when any pill (canonical or custom) is selected. Always carries the labelValue. */
  onSelectName: (name: string) => void;
};

export function SkillHotBar({
  selectedSkillName,
  onSelectId,
  onSelectName
}: SkillHotBarProps) {
  const customSkills = useCustomSkills();
  const [adding, setAdding] = useState(false);

  return (
    <div className="skill-hot-bar" role="toolbar" aria-label="Skill picker">
      {HUMANOID_SKILLS.map((skill) => {
        const isActive = skill.name === selectedSkillName;
        // Skill 0 (approach) loses its keyboard shortcut — digit "0" cancels the
        // current draft instead. Show a click-only marker on its chip so users
        // don't expect a 0 keystroke to pick approach.
        const clickOnly = skill.id === 0;
        return (
          <button
            key={skill.id}
            type="button"
            className={`skill-chip${isActive ? " active" : ""}${clickOnly ? " click-only" : ""}`}
            onClick={() => {
              onSelectId(skill.id);
              onSelectName(skill.name);
            }}
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
      {customSkills.map((skill) => {
        const isActive = skill.name === selectedSkillName;
        return (
          <span
            key={skill.name}
            className={`skill-chip skill-chip-custom${isActive ? " active" : ""}`}
            style={{ ["--skill-color" as string]: skill.color }}
          >
            <button
              type="button"
              className="skill-chip-main"
              onClick={() => onSelectName(skill.name)}
              title={`${skill.label} — custom skill (no keyboard shortcut)`}
            >
              <span className="skill-chip-key" aria-hidden>
                ·
              </span>
              <span className="skill-chip-label">{skill.label}</span>
            </button>
            <button
              type="button"
              className="skill-chip-remove"
              onClick={(event) => {
                event.stopPropagation();
                removeCustomSkill(skill.name);
                if (selectedSkillName === skill.name) {
                  onSelectId(0);
                  onSelectName(HUMANOID_SKILLS[0].name);
                }
              }}
              aria-label={`Remove custom skill ${skill.name}`}
              title="Remove custom skill"
            >
              <X size={10} />
            </button>
          </span>
        );
      })}
      {adding ? (
        <span className="skill-chip-combobox-slot">
          <SkillCombobox
            value=""
            autoFocus
            placeholder="search skills or add new…"
            onChange={(name) => {
              onSelectName(name);
              setAdding(false);
            }}
            onCancel={() => setAdding(false)}
          />
          <button
            type="button"
            className="skill-chip-add-cancel"
            onClick={() => setAdding(false)}
            title="Cancel"
            aria-label="Cancel adding skill"
          >
            <X size={12} />
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="skill-chip skill-chip-add"
          onClick={() => setAdding(true)}
          title="Search existing skills or add a new custom one"
          aria-label="Search or add skill"
        >
          <Plus size={12} />
        </button>
      )}
    </div>
  );
}
