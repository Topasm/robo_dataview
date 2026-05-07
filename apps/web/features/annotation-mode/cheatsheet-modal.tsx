"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

type CheatsheetModalProps = {
  open: boolean;
  onClose: () => void;
  enableBadFrameShortcuts: boolean;
  onSetEnableBadFrameShortcuts: (next: boolean) => void;
};

type ShortcutRow = { keys: string[]; description: string };
type ShortcutGroup = { title: string; rows: ShortcutRow[] };

const ALWAYS_ON_GROUP: ShortcutGroup = {
  title: "Anywhere",
  rows: [
    { keys: ["?"], description: "Show / hide this cheatsheet" },
    { keys: ["Esc"], description: "Close cheatsheet or drawer" }
  ]
};

const BROWSE_GROUPS: ShortcutGroup[] = [
  {
    title: "Browse — playback",
    rows: [
      { keys: ["Space"], description: "Play / pause current episode" },
      { keys: ["←", "→"], description: "Step 1 frame  (Shift = ±10)" }
    ]
  },
  {
    title: "Browse — episode list",
    rows: [
      { keys: ["↑", "↓"], description: "Previous / next episode" },
      { keys: ["Enter"], description: "Open current episode in Annotate" }
    ]
  },
  {
    title: "Browse — disposition",
    rows: [
      { keys: ["K"], description: "Mark episode as Kept" },
      { keys: ["X"], description: "Mark episode as Deleted (soft)" },
      { keys: ["F"], description: "Flag episode for follow-up" }
    ]
  }
];

const ANNOTATE_GROUPS: ShortcutGroup[] = [
  {
    title: "Annotate — playback",
    rows: [
      { keys: ["Space"], description: "Play / pause" },
      { keys: ["←", "→"], description: "Step 1 frame  (Shift = ±10)" }
    ]
  },
  {
    title: "Annotate — cut clips",
    rows: [
      { keys: ["I"], description: "Mark in (start frame)" },
      { keys: ["O"], description: "Mark out (end frame)" },
      {
        keys: ["1", "…", "9"],
        description: "Pick skill 1–9 — when both I & O are set, instantly create + accept clip"
      },
      { keys: ["0"], description: "Cancel current draft (clear I/O markers)" },
      { keys: ["Backspace"], description: "Delete selected clip" }
    ]
  }
];

const BAD_FRAME_GROUP: ShortcutGroup = {
  title: "Annotate — bad-frame (opt-in)",
  rows: [
    { keys: ["M"], description: "Toggle current frame as bad" },
    { keys: ["B"], description: "Add bad range around current frame" }
  ]
};

export function CheatsheetModal({
  open,
  onClose,
  enableBadFrameShortcuts,
  onSetEnableBadFrameShortcuts
}: CheatsheetModalProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const groups: ShortcutGroup[] = [
    ALWAYS_ON_GROUP,
    ...BROWSE_GROUPS,
    ...ANNOTATE_GROUPS,
    ...(enableBadFrameShortcuts ? [BAD_FRAME_GROUP] : [])
  ];

  return (
    <div
      className="cheatsheet-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="cheatsheet-modal" role="dialog" aria-label="Keyboard shortcuts">
        <header className="cheatsheet-header">
          <h2>Keyboard shortcuts</h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close shortcuts"
          >
            <X size={16} />
          </button>
        </header>
        <div className="cheatsheet-body">
          {groups.map((group) => (
            <section key={group.title} className="cheatsheet-group">
              <h3>{group.title}</h3>
              <dl>
                {group.rows.map((row) => (
                  <div key={row.description} className="cheatsheet-row">
                    <dt>
                      {row.keys.map((key, index) => (
                        <span key={`${row.description}-${index}`}>
                          <kbd>{key}</kbd>
                          {index < row.keys.length - 1 ? <span className="cheatsheet-sep">+</span> : null}
                        </span>
                      ))}
                    </dt>
                    <dd>{row.description}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <footer className="cheatsheet-footer">
          <label className="cheatsheet-toggle">
            <input
              type="checkbox"
              checked={enableBadFrameShortcuts}
              onChange={(event) => onSetEnableBadFrameShortcuts(event.target.checked)}
            />
            <span>Enable bad-frame shortcuts (M / B)</span>
          </label>
        </footer>
      </div>
    </div>
  );
}
