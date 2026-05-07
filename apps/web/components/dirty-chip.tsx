"use client";

import { CheckCircle2, CircleDot } from "lucide-react";

type DirtyChipProps = {
  count: number;
  onJumpToFirst?: () => void;
};

export function DirtyChip({ count, onJumpToFirst }: DirtyChipProps) {
  if (count <= 0) {
    return (
      <span className="dirty-chip dirty-chip--clean" title="No annotations are waiting to be applied">
        <CheckCircle2 size={13} />
        <span>Up to date</span>
      </span>
    );
  }
  const label = `${count} episode${count === 1 ? "" : "s"} edited since last apply`;
  if (!onJumpToFirst) {
    return (
      <span className="dirty-chip dirty-chip--dirty" title={label}>
        <CircleDot size={13} />
        <span>{label}</span>
      </span>
    );
  }
  return (
    <button
      type="button"
      className="dirty-chip dirty-chip--dirty dirty-chip--clickable"
      onClick={onJumpToFirst}
      title={`${label}. Click to jump to the first edited episode.`}
      aria-label={label}
    >
      <CircleDot size={13} />
      <span>{label}</span>
    </button>
  );
}
