import { SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type { SegmentAnnotation } from "@/lib/types";

export type ClipOverlap = {
  otherId: string;
  otherSkill: string;
  otherStart: number;
  otherEnd: number;
};

type GroupKey = string;

function groupKey(annotation: SegmentAnnotation): GroupKey {
  return `${annotation.datasetId}::${annotation.episodeIndex}`;
}

function eligibleSkillClips(annotations: SegmentAnnotation[]): SegmentAnnotation[] {
  return annotations.filter(
    (annotation) =>
      annotation.labelType === SKILL_LABEL_TYPE && annotation.reviewStatus === "accepted"
  );
}

function groupByEpisode(annotations: SegmentAnnotation[]): Map<GroupKey, SegmentAnnotation[]> {
  const groups = new Map<GroupKey, SegmentAnnotation[]>();
  for (const annotation of annotations) {
    const key = groupKey(annotation);
    const bucket = groups.get(key);
    if (bucket) {
      bucket.push(annotation);
    } else {
      groups.set(key, [annotation]);
    }
  }
  return groups;
}

function rangesOverlap(a: SegmentAnnotation, b: SegmentAnnotation): boolean {
  return a.startFrame <= b.endFrame && b.startFrame <= a.endFrame;
}

/**
 * For accepted skill clips within the same episode, find pairs whose frame
 * ranges overlap (inclusive). Returns a Map keyed by clip id, where each value
 * lists every overlapping partner. Both clips of an overlapping pair appear in
 * the map.
 */
export function findClipOverlaps(
  annotations: SegmentAnnotation[]
): Map<string, ClipOverlap[]> {
  const overlaps = new Map<string, ClipOverlap[]>();
  const groups = groupByEpisode(eligibleSkillClips(annotations));

  for (const clips of groups.values()) {
    for (let i = 0; i < clips.length; i += 1) {
      const a = clips[i];
      for (let j = i + 1; j < clips.length; j += 1) {
        const b = clips[j];
        if (!rangesOverlap(a, b)) {
          continue;
        }
        appendOverlap(overlaps, a, b);
        appendOverlap(overlaps, b, a);
      }
    }
  }

  return overlaps;
}

function appendOverlap(
  map: Map<string, ClipOverlap[]>,
  source: SegmentAnnotation,
  partner: SegmentAnnotation
): void {
  const entry: ClipOverlap = {
    otherId: partner.id,
    otherSkill: partner.labelValue,
    otherStart: partner.startFrame,
    otherEnd: partner.endFrame
  };
  const existing = map.get(source.id);
  if (existing) {
    existing.push(entry);
  } else {
    map.set(source.id, [entry]);
  }
}

/**
 * Counts distinct unordered overlapping pairs (so a single conflict between
 * clip A and clip B counts as 1, not 2).
 */
export function countOverlappingPairs(annotations: SegmentAnnotation[]): number {
  const groups = groupByEpisode(eligibleSkillClips(annotations));
  let pairs = 0;
  for (const clips of groups.values()) {
    for (let i = 0; i < clips.length; i += 1) {
      const a = clips[i];
      for (let j = i + 1; j < clips.length; j += 1) {
        if (rangesOverlap(a, clips[j])) {
          pairs += 1;
        }
      }
    }
  }
  return pairs;
}
