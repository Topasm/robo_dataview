"use client";

import { useEffect, useState } from "react";

/**
 * User-defined skill names that live alongside the canonical 10 in
 * `humanoid_skills.json`. They show up in the SkillCombobox autocomplete
 * and in chart legends, but they are NOT registered as canonical skills:
 * exporting a Lance Training Bundle still rejects them (see CLAUDE.md
 * "Skill vocabulary contract"), so this is purely a local exploration
 * affordance — useful for prototyping new boundaries before promoting a
 * name to the canonical registry.
 *
 * Storage: localStorage keyed at `STORAGE_KEY` so the choices survive
 * reloads on the same machine. Cross-machine sync would require an API
 * endpoint, intentionally out of scope.
 */
export type CustomSkill = {
  /** Machine-readable name; also the labelValue stored on annotations. */
  name: string;
  /** Display label, defaults to a humanized version of `name`. */
  label: string;
  /** Color for chart bands and inspector chips. */
  color: string;
};

const STORAGE_KEY = "rds.customSkills";
const CHANGE_EVENT = "rds:custom-skills-changed";

const FALLBACK_PALETTE = [
  "#06b6d4",
  "#a855f7",
  "#f97316",
  "#22c55e",
  "#ec4899",
  "#eab308",
  "#14b8a6",
  "#3b82f6"
];

function safeParse(raw: string | null): CustomSkill[] {
  if (!raw) return [];
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return value.filter(
      (item): item is CustomSkill =>
        typeof item === "object" &&
        item !== null &&
        typeof item.name === "string" &&
        typeof item.label === "string" &&
        typeof item.color === "string"
    );
  } catch {
    return [];
  }
}

export function getCustomSkills(): CustomSkill[] {
  if (typeof window === "undefined") return [];
  return safeParse(window.localStorage.getItem(STORAGE_KEY));
}

function writeCustomSkills(next: CustomSkill[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function humanizeSkillName(name: string): string {
  return name
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function addCustomSkill(rawName: string): CustomSkill | null {
  const name = rawName.trim().toLowerCase().replace(/\s+/g, "_");
  if (!name) return null;
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) return null;
  const existing = getCustomSkills();
  const found = existing.find((skill) => skill.name === name);
  if (found) return found;
  const next: CustomSkill = {
    name,
    label: humanizeSkillName(name),
    color: FALLBACK_PALETTE[existing.length % FALLBACK_PALETTE.length]
  };
  writeCustomSkills([...existing, next]);
  return next;
}

export function removeCustomSkill(name: string): void {
  const next = getCustomSkills().filter((skill) => skill.name !== name);
  writeCustomSkills(next);
}

export function useCustomSkills(): CustomSkill[] {
  const [skills, setSkills] = useState<CustomSkill[]>(() => getCustomSkills());
  useEffect(() => {
    if (typeof window === "undefined") return;
    function handler() {
      setSkills(getCustomSkills());
    }
    window.addEventListener(CHANGE_EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(CHANGE_EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);
  return skills;
}
