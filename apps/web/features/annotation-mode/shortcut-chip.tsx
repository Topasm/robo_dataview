"use client";

type ShortcutChipProps = {
  enableBadFrameShortcuts: boolean;
};

type Hint = { keys: string[]; label: string };

const BASE_HINTS: Hint[] = [
  { keys: ["Space"], label: "play / pause" },
  { keys: ["←", "→"], label: "step (Shift = ±10)" },
  { keys: ["I"], label: "in" },
  { keys: ["O"], label: "out" },
  { keys: ["1", "–", "9"], label: "skill" },
  { keys: ["0"], label: "cancel draft" },
  { keys: ["⌫"], label: "delete clip" },
  { keys: ["?"], label: "help" }
];

const BAD_FRAME_HINTS: Hint[] = [
  { keys: ["M"], label: "bad frame" },
  { keys: ["B"], label: "bad range" }
];

export function ShortcutChip({ enableBadFrameShortcuts }: ShortcutChipProps) {
  const hints = enableBadFrameShortcuts ? [...BASE_HINTS, ...BAD_FRAME_HINTS] : BASE_HINTS;
  return (
    <div className="shortcut-chip" role="status" aria-label="Annotate keyboard hints">
      {hints.map((hint, index) => (
        <span key={`${hint.label}-${index}`} className="shortcut-chip-item">
          <span className="shortcut-chip-keys">
            {hint.keys.map((key, kindex) =>
              key === "–" || key === "+" ? (
                <span key={kindex} className="shortcut-chip-sep">
                  {key}
                </span>
              ) : (
                <kbd key={kindex}>{key}</kbd>
              )
            )}
          </span>
          <span className="shortcut-chip-label">{hint.label}</span>
        </span>
      ))}
    </div>
  );
}
