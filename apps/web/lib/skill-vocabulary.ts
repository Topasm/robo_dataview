/**
 * Humanoid skill vocabulary — Notion Mission Breakdown + Data Collection Plan 기준.
 *
 * 전체 trajectory에서 추출하는 단위 행동(skill) 목록.
 * label_type = "skill", label_value = skill.name 으로 segment DB에 저장됨.
 */

export type HumanoidSkill = {
  /** Numeric skill id (0–9), used for keyboard shortcuts */
  id: number;
  /** Machine-readable name, stored as label_value */
  name: string;
  /** Human-readable display label */
  label: string;
  /** Unique color for timeline / list badges */
  color: string;
};

export const HUMANOID_SKILLS: readonly HumanoidSkill[] = [
  { id: 0, name: "approach", label: "Approach", color: "#4A90D9" },
  { id: 1, name: "grasp_part", label: "Grasp Part", color: "#50C878" },
  { id: 2, name: "grasp_bolt", label: "Grasp Bolt", color: "#8B5CF6" },
  { id: 3, name: "insert_bolt", label: "Insert Bolt", color: "#F59E0B" },
  { id: 4, name: "place", label: "Place", color: "#EF4444" },
  { id: 5, name: "push_button", label: "Push Button", color: "#EC4899" },
  { id: 6, name: "grasp_drill", label: "Grasp Drill", color: "#14B8A6" },
  { id: 7, name: "drill_trigger", label: "Drill Trigger", color: "#F97316" },
  { id: 8, name: "bimanual_grasp", label: "Bimanual Grasp", color: "#6366F1" },
  { id: 9, name: "insert_tire", label: "Insert Tire", color: "#0EA5E9" },
] as const;

/** Segment label_type used for all skill clips */
export const SKILL_LABEL_TYPE = "skill" as const;

/** Look up a skill by numeric id */
export function skillById(id: number): HumanoidSkill | undefined {
  return HUMANOID_SKILLS.find((s) => s.id === id);
}

/** Look up a skill by name (label_value in DB) */
export function skillByName(name: string): HumanoidSkill | undefined {
  return HUMANOID_SKILLS.find((s) => s.name === name);
}
