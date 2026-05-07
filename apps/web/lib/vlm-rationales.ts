/**
 * VLM rationale extraction.
 *
 * VLM responses (`VlmResponseRecord.rawResponse.parsed_rationales`) are keyed
 * by skill name (e.g. `approach`, `grasp_part`). Each value is either a single
 * `{label, confidence, rationale}` object or an array of them (when the model
 * proposes multiple instances of the same skill in the episode).
 *
 * Because pending clips coming back from the VLM share that same skill-name
 * key as their `labelValue`, looking up the rationale is a `Map.get(skillName)`
 * followed by index ordering.
 */

import type { VlmResponseRecord } from "@/lib/types";

export type VlmRationale = {
  label: string;
  confidence: number | null;
  rationale: string | null;
};

function objectValue(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function objectField(payload: Record<string, unknown>, key: string): Record<string, unknown> | null {
  return objectValue(payload[key]);
}

function stringField(payload: Record<string, unknown> | null, key: string): string | null {
  if (!payload) return null;
  const v = payload[key];
  return typeof v === "string" ? v : null;
}

function numberField(payload: Record<string, unknown> | null, key: string): number | null {
  if (!payload) return null;
  const v = payload[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function toRationale(metadata: Record<string, unknown>, fallbackLabel: string): VlmRationale {
  return {
    label: stringField(metadata, "label") ?? fallbackLabel,
    confidence: numberField(metadata, "confidence"),
    rationale: stringField(metadata, "rationale")
  };
}

/**
 * Build a `Map<skillName, VlmRationale[]>` from all VLM responses for the
 * current episode. Same-skill rationales are listed in source order so callers
 * can match the Nth pending clip with the Nth rationale entry.
 */
export function buildRationaleMap(responses: VlmResponseRecord[]): Map<string, VlmRationale[]> {
  const map = new Map<string, VlmRationale[]>();
  for (const response of responses) {
    const rationales = objectField(response.rawResponse, "parsed_rationales");
    if (!rationales) continue;
    for (const [key, value] of Object.entries(rationales)) {
      const list = map.get(key) ?? [];
      if (Array.isArray(value)) {
        for (const item of value) {
          const meta = objectValue(item);
          if (meta) list.push(toRationale(meta, key));
        }
      } else {
        const meta = objectValue(value);
        if (meta) list.push(toRationale(meta, key));
      }
      map.set(key, list);
    }
  }
  return map;
}

/**
 * Format the first rationale entry for a skill as a tooltip-friendly string.
 * Returns null when there is nothing to show.
 */
export function formatRationaleTooltip(rationale: VlmRationale | undefined): string | null {
  if (!rationale) return null;
  if (!rationale.rationale && rationale.confidence === null) return null;
  const parts: string[] = [];
  if (rationale.confidence !== null) {
    parts.push(`confidence ${rationale.confidence.toFixed(2)}`);
  }
  if (rationale.rationale) {
    parts.push(rationale.rationale);
  }
  return parts.length > 0 ? `VLM: ${parts.join(" — ")}` : null;
}
