"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";

import {
  addCustomSkill,
  removeCustomSkill,
  useCustomSkills
} from "@/lib/custom-skills";
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
  const [draftName, setDraftName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  function commitNew() {
    const created = addCustomSkill(draftName);
    if (created) {
      onSelectName(created.name);
    }
    setDraftName("");
    setAdding(false);
  }

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
        <span className="skill-chip skill-chip-add-input">
          <input
            ref={inputRef}
            type="text"
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitNew();
              } else if (event.key === "Escape") {
                event.preventDefault();
                setDraftName("");
                setAdding(false);
              }
            }}
            placeholder="new_skill_name"
            aria-label="New skill name"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            className="skill-chip-add-confirm"
            onClick={commitNew}
            disabled={!draftName.trim()}
            aria-label="Add new custom skill"
          >
            ✓
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="skill-chip skill-chip-add"
          onClick={() => setAdding(true)}
          title="Add a new custom skill (export still rejects non-canonical labels)"
          aria-label="Add custom skill"
        >
          <Plus size={12} />
        </button>
      )}
    </div>
  );
}
